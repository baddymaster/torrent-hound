"""YTS source: movies only, JSON API, no scraping."""

import re
import urllib.parse

import requests

from torrent_hound import state
from torrent_hound.ui import colored

# Per the YTS API documentation page (https://yts.bz/api), the canonical v2
# base URL is `https://movies-api.accel.li/api/v2/`. The four yts.* mirrors
# remain on the list as fallbacks: they share the same backend (all redirect
# to or are served by yts.bz) and continued working at the time of writing,
# but the operator's own docs explicitly direct callers to accel.li and the
# old endpoint's published `sunset` (2026-04-10) has already passed.
YTS_DOMAINS = ['movies-api.accel.li', 'yts.lt', 'yts.am', 'yts.bz', 'yts.gg']

# Hosts that only serve the API — no movie pages. The API's response carries
# a real `url` field pointing at e.g. `https://yts.bz/movies/...`; for these
# hosts we leave the URL alone instead of rewriting it (rewriting to the API
# host would produce a link that returns JSON, not a viewable page).
_YTS_API_ONLY_HOSTS = {'movies-api.accel.li'}

# YTS's `query_term` does substring matching against movie titles only — no
# inline DSL. Tokens like "1080p" appended to a query won't match any title
# and silently produce zero results. The dedicated `quality=` API parameter
# is the right channel for this. We extract recognised quality tokens out of
# the query and route them to that parameter so users can keep typing
# fluent queries like "the matrix 1080p" and get expected results.
# Canonical YTS quality values (case-sensitive on the API side; we normalise
# user input to these).
_YTS_QUALITY_VALUES = {
    '480p': '480p',
    '720p': '720p',
    '1080p': '1080p',
    '1080p.x265': '1080p.x265',
    '2160p': '2160p',
    '3d': '3D',
}


def _extract_yts_quality(query):
    """Pull a YTS-supported quality token out of `query`. Returns
    `(cleaned_query, quality_param_value_or_None)`. Case-insensitive; first
    matching token wins (subsequent quality tokens are left in the query
    untouched, since YTS only accepts one quality at a time)."""
    if not query:
        return query, None
    quality = None
    kept = []
    for tok in query.split():
        norm = tok.lower()
        if quality is None and norm in _YTS_QUALITY_VALUES:
            quality = _YTS_QUALITY_VALUES[norm]
            continue
        kept.append(tok)
    return ' '.join(kept), quality


# Recommended trackers per the YTS API documentation page (https://yts.bz/api),
# in the order listed there. More trackers in a magnet means better swarm
# discovery for clients that honour them all (most do). Includes three HTTPS
# trackers — `tr=https://...` is standard and accepted by mainline clients.
YTS_TRACKERS = [
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://tracker.torrent.eu.org:451/announce",
    "udp://tracker.dler.org:6969/announce",
    "udp://open.stealth.si:80/announce",
    "udp://open.demonii.com:1337/announce",
    "https://tracker.moeblog.cn:443/announce",
    "udp://open.dstud.io:6969/announce",
    "udp://tracker.srv00.com:6969/announce",
    "https://tracker.zhuqiy.com:443/announce",
    "https://tracker.pmman.tech:443/announce",
]


def _build_yts_magnet(info_hash, title):
    dn = urllib.parse.quote_plus(title)
    trackers = "&".join(f"tr={t}" for t in YTS_TRACKERS)
    return f"magnet:?xt=urn:btih:{info_hash}&dn={dn}&{trackers}"


def _parse_yts_json(data, domain='yts.mx', limit=10, quality_filter=None):
    """Flatten YTS API response into a list of result dicts (one per quality variant).

    `quality_filter`, when set, drops torrents whose `quality` doesn't match.
    The YTS `quality=` API parameter filters which *movies* are returned (a
    movie qualifies if it has any torrent of that quality), but the response
    still carries every torrent variant for each matched movie. Without this
    client-side filter, a user query like "matrix 1080p" still surfaces 720p
    and 2160p rows alongside the 1080p one they actually asked for.
    """
    movies = data.get("data", {}).get("movies") or []
    parsed = []
    for movie in movies:
        # Rewrite the link to use the responding mirror, except for API-only
        # hosts (movies-api.accel.li) which don't serve movie pages — for those
        # we trust the API's returned URL (already a real yts.bz/movies/... page).
        movie_url = movie.get("url", "")
        if movie_url and domain not in _YTS_API_ONLY_HOSTS:
            movie_url = re.sub(r'https?://[^/]+', f'https://{domain}', movie_url)
        for torrent in movie.get("torrents", []):
            if quality_filter and torrent.get('quality') != quality_filter:
                continue
            name = f"{movie.get('title_long', movie.get('title', '?'))} [{torrent['quality']}]"
            seeds = torrent.get("seeds", 0)
            peers = torrent.get("peers", 0)
            try:
                ratio = format(float(seeds) / float(peers), '.1f')
            except ZeroDivisionError:
                ratio = 'inf'
            parsed.append({
                "name": name,
                "link": movie_url,
                "seeders": seeds,
                "leechers": peers,
                "size": torrent.get("size", "?"),
                "ratio": ratio,
                "magnet": _build_yts_magnet(torrent["hash"], name),
            })
            if len(parsed) >= limit:
                return parsed
    return parsed


def searchYTS(search_string='', quiet_mode=False, limit=10, timeout=8, progress=None):
    """Search YTS, trying known mirrors in order."""
    clean_query, quality = _extract_yts_quality(search_string)
    params = [
        ('query_term', clean_query),
        ('limit', '20'),
        ('sort_by', 'seeds'),
    ]
    if quality is not None:
        params.append(('quality', quality))
    qs = urllib.parse.urlencode(params)
    for domain in YTS_DOMAINS:
        url = f"https://{domain}/api/v2/list_movies.json?{qs}"
        if progress:
            progress({"type": "mirror_attempt", "mirror": domain})
        try:
            r = requests.get(url, timeout=timeout)
            data = r.json()
            if data.get("status") == "ok":
                # API responded successfully but has no usable matches → genuine
                # empty, not a mirror failure. Two shapes both land here:
                #   movie_count==0 + no `movies` key (e.g. "ubuntu" — no hits)
                #   movie_count>0 but `movies` array missing/empty (e.g. wrong
                #     year: "the devil wears prada 2026" pre-counts the 2006
                #     match then filters it out).
                # Either way, walking more mirrors can't conjure results;
                # they all share the same backend.
                movies = data.get("data", {}).get("movies") or []
                if not movies:
                    if progress:
                        progress({"type": "empty"})
                    return []
                # Use the post-redirect host so links point to the domain that
                # actually served us (e.g. yts.lt → yts.bz). Fall back to the
                # requested domain if r.url is somehow empty.
                serving_domain = urllib.parse.urlparse(r.url).netloc or domain
                parsed = _parse_yts_json(data, domain=serving_domain, limit=limit, quality_filter=quality)
                if parsed:
                    state.yts_url = url
                    if progress:
                        progress({"type": "ok", "count": len(parsed), "mirror": serving_domain})
                    return parsed
            # Mirror responded but no parseable results — treat as miss.
            if progress:
                progress({"type": "mirror_failed", "mirror": domain})
        except (requests.RequestException, ValueError):
            if progress:
                progress({"type": "mirror_failed", "mirror": domain})
            continue
    if not quiet_mode:
        print(colored.magenta("[YTS] Error : All known mirrors returned no results or were unreachable"))
    if progress:
        progress({"type": "failed"})
    return []
