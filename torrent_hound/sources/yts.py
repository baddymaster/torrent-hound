"""YTS source: movies only, JSON API, no scraping."""

import re
import urllib.parse

import requests

from torrent_hound import state
from torrent_hound.ui import colored

YTS_DOMAINS = ['yts.lt', 'yts.am', 'yts.mx', 'yts.rs', 'yts.bz', 'yts.gg']

YTS_TRACKERS = [
    "udp://open.demonii.com:1337/announce",
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://tracker.torrent.eu.org:451/announce",
    "udp://tracker.dler.org:6969/announce",
    "udp://open.stealth.si:80/announce",
]


def _build_yts_magnet(info_hash, title):
    dn = urllib.parse.quote_plus(title)
    trackers = "&".join(f"tr={t}" for t in YTS_TRACKERS)
    return f"magnet:?xt=urn:btih:{info_hash}&dn={dn}&{trackers}"


def _parse_yts_json(data, domain='yts.mx', limit=10):
    """Flatten YTS API response into a list of result dicts (one per quality variant)."""
    movies = data.get("data", {}).get("movies") or []
    parsed = []
    for movie in movies:
        # Rewrite the link to use the working domain instead of whatever the API returned
        movie_url = movie.get("url", "")
        if movie_url:
            # Replace any YTS domain in the URL with the one that actually responded
            movie_url = re.sub(r'https?://[^/]+', f'https://{domain}', movie_url)
        for torrent in movie.get("torrents", []):
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
    for domain in YTS_DOMAINS:
        url = f"https://{domain}/api/v2/list_movies.json?query_term={urllib.parse.quote_plus(search_string)}&limit=20&sort_by=seeds"
        if progress:
            progress({"type": "mirror_attempt", "mirror": domain})
        try:
            r = requests.get(url, timeout=timeout)
            data = r.json()
            if data.get("status") == "ok":
                # API says "ok" with zero movies → genuine empty result, not a
                # mirror failure. Probing more domains won't change the answer
                # (YTS is movies-only; queries like "ubuntu" naturally return 0).
                if data.get("data", {}).get("movie_count", 0) == 0:
                    if progress:
                        progress({"type": "empty"})
                    return []
                parsed = _parse_yts_json(data, domain=domain, limit=limit)
                if parsed:
                    state.yts_url = url
                    if progress:
                        progress({"type": "ok", "count": len(parsed), "mirror": domain})
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
