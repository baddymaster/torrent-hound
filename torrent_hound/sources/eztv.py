"""EZTV source: TV shows via IMDB ID bridge, JSON API, episode/quality filtering."""

import re

import requests

from torrent_hound import state
from torrent_hound.ui import colored

from .base import _extract_release_tags, _fmt_date, _format_bytes

EZTV_DOMAINS = ['eztvx.to', 'eztv.wf', 'eztv.tf', 'eztv.yt', 'eztv.it']


def _parse_episode_query(query):
    """Extract show name, season, episode, and extra keyword filters from a search query.

    Returns (clean_query, season, episode, filters) where season/episode are
    strings (leading zeros stripped) or None, and filters is a list of leftover
    tokens like ['1080p', 'x265'].
    """
    season, episode = None, None
    ep_match = re.search(r'(?i)\bs(\d{1,2})(?:e(\d{1,2}))?\b', query)
    if ep_match:
        season = str(int(ep_match.group(1)))  # strip leading zeros
        if ep_match.group(2):
            episode = str(int(ep_match.group(2)))
        # Remove the SxxExx part from the query
        query = query[:ep_match.start()] + query[ep_match.end():]

    # Split what remains: the first meaningful words are the show name,
    # any leftover tokens (1080p, x265, hevc, web-dl, etc.) are filters.
    # Heuristic: known filter-like patterns vs. show-name words.
    _FILTER_RE = re.compile(
        r'^(?:\d{3,4}p|[xh]\.?26[45]|hevc|avc|web[- ]?dl|bluray|remux|hdr|uhd|'
        r'dts|aac|atmos|ddp?\d?\.?\d?|proper|repack|internal)$',
        re.IGNORECASE,
    )
    words = query.strip().split()
    clean_words, filter_words = [], []
    for w in words:
        if _FILTER_RE.match(w):
            filter_words.append(w.lower())
        else:
            clean_words.append(w)
    clean_query = ' '.join(clean_words).strip()
    return clean_query, season, episode, filter_words


def _imdb_lookup_candidates(query, timeout=8, limit=5):
    """Return up to `limit` (id, suggestion_item) pairs of tvSeries matches
    for `query`, in IMDB suggestion order (most relevant first). The id is
    the numeric form (without 'tt' prefix); the suggestion_item is the raw
    dict so callers can pluck extra fields (`s` = top cast, `y` = year)
    without re-fetching.

    Multi-candidate is critical for franchise queries where IMDB has
    several distinct `tvSeries` entries (e.g. multiple spin-offs or
    sequels under one umbrella name). EZTV's API is keyed by IMDB ID, so
    picking only the first suggestion misses everything tagged under the
    others. Returns an empty list on any failure (network / non-JSON /
    no tvSeries match).
    """
    slug = query.strip().replace(' ', '_').lower()
    if not slug:
        return []
    url = f'https://v2.sg.media-imdb.com/suggestion/{slug[0]}/{slug}.json'
    try:
        r = requests.get(url, timeout=timeout)
        out = []
        for item in r.json().get('d', []):
            if item.get('qid') == 'tvSeries':
                out.append((item['id'].removeprefix('tt'), item))
                if len(out) >= limit:
                    break
        return out
    except (requests.RequestException, ValueError, KeyError):
        return []


def _imdb_lookup(query, timeout=8):
    """Single-result wrapper around `_imdb_lookup_candidates`. Returns the
    most-relevant tvSeries IMDB ID (without 'tt' prefix) or None.
    Preserved for back-compat — callers needing the suggestion item
    should use `_imdb_lookup_candidates` directly."""
    candidates = _imdb_lookup_candidates(query, timeout=timeout, limit=1)
    return candidates[0][0] if candidates else None


def _eztv_slug(title):
    """Derive a URL slug from an EZTV torrent title."""
    clean = re.sub(r'\s*EZTV$', '', title, flags=re.IGNORECASE)
    return re.sub(r'[^a-z0-9]+', '-', clean.lower()).strip('-')


def _parse_eztv_json(torrents, domain='eztvx.to', season=None, episode=None, filters=None, limit=10):
    """Filter and convert raw EZTV torrent dicts into our standard result format."""
    parsed = []
    for t in torrents:
        # Season / episode filter
        if season and t.get('season') != season:
            continue
        if episode and t.get('episode') != episode:
            continue
        # Keyword filters (all must match in title, case-insensitive)
        title = t.get('title', '') or t.get('filename', '')
        if filters:
            title_lower = title.lower()
            if not all(f in title_lower for f in filters):
                continue
        seeds = t.get('seeds', 0)
        peers = t.get('peers', 0)
        try:
            ratio = format(float(seeds) / float(peers), '.1f')
        except (ZeroDivisionError, ValueError):
            ratio = 'inf'
        size_bytes = t.get('size_bytes', 0)
        metadata: dict = {"name": title}
        if t.get('imdb_id'):
            metadata['imdb_code'] = f"tt{t['imdb_id']}"
        season_val = t.get('season')
        if season_val and str(season_val) != '0':
            try:
                metadata['season'] = int(season_val)
            except (TypeError, ValueError):
                pass
        episode_val = t.get('episode')
        if episode_val and str(episode_val) != '0':
            try:
                metadata['episode'] = int(episode_val)
            except (TypeError, ValueError):
                pass
        uploaded = _fmt_date(t.get('date_released_unix'))
        if uploaded:
            metadata['uploaded'] = uploaded
            metadata['released'] = uploaded   # episode air-date (overridden by IMDB year if available)
        # Title regex for quality/codec/source/repack
        metadata.update(_extract_release_tags(title))
        parsed.append({
            'name': title,
            'link': f"https://{domain}/ep/{t.get('id', '')}/{_eztv_slug(title)}/",
            'seeders': seeds,
            'leechers': peers,
            'size': _format_bytes(size_bytes),
            'ratio': ratio,
            'magnet': t.get('magnet_url', ''),
            'metadata': metadata,
        })
        if len(parsed) >= limit:
            break
    return parsed


def _fetch_eztv_torrents_for_id(imdb_id, domain, timeout):
    """Fetch all torrents for one IMDB ID from one EZTV domain, paginating
    up to 3 pages (~300 episodes). Returns `(torrents, status)` where status
    is one of:

      'ok'            — got ≥1 torrent
      'empty'         — API explicitly returned `torrents_count: 0`; the
                        IMDB ID matched nothing on EZTV's backend. Caller
                        should not retry on other mirrors (same backend),
                        but may try a different IMDB candidate.
      'mirror_failed' — network/JSON error or unexpected shape; caller
                        should try the next mirror for this IMDB ID.
    """
    all_torrents = []
    try:
        for page in range(1, 4):
            url = f"https://{domain}/api/get-torrents?imdb_id={imdb_id}&limit=100&page={page}"
            r = requests.get(url, timeout=timeout)
            data = r.json()
            # Explicit zero count from the API on the first page → definitive
            # empty for this IMDB ID. Don't probe further mirrors; their
            # backend is the same.
            if page == 1 and data.get('torrents_count') == 0:
                return [], 'empty'
            page_torrents = data.get('torrents', [])
            if not page_torrents:
                break
            all_torrents.extend(page_torrents)
            if len(all_torrents) >= data.get('torrents_count', 0):
                break
    except (requests.RequestException, ValueError):
        return [], 'mirror_failed'
    if all_torrents:
        return all_torrents, 'ok'
    return [], 'mirror_failed'


def searchEZTV(search_string='', quiet_mode=False, limit=10, timeout=8, progress=None):
    """Search EZTV via the IMDB-ID bridge with optional episode/quality
    filtering. When IMDB returns multiple tvSeries candidates for a query
    (common for franchise queries that span several spin-offs), we walk
    the candidate list in order, aggregating torrents from any that EZTV
    actually hosts. Stops early once we have plenty of headroom for
    filtering."""
    clean_query, season, episode, filters = _parse_episode_query(search_string)

    candidates = _imdb_lookup_candidates(clean_query, timeout=timeout)
    if not candidates:
        if not quiet_mode:
            print(colored.magenta("[EZTV] No matching TV show found on IMDB"))
        if progress:
            progress({"type": "empty"})
        return []

    # Build a lookup from imdb_id → enrichment dict (cast + year) sourced from
    # the IMDB suggestion items we already have. Free metadata; merged into
    # each result row's `metadata` dict after parsing.
    imdb_enrichment: dict = {}
    for imdb_id, item in candidates:
        enrich: dict = {}
        if item.get("s"):
            enrich["cast"] = item["s"]
        if item.get("y"):
            enrich["released"] = str(item["y"])
        imdb_enrichment[imdb_id] = enrich

    all_torrents = []
    working_domain = EZTV_DOMAINS[0]
    any_ok_or_empty = False  # at least one mirror responded for any candidate
    target = max(limit * 3, 30)  # soft cap with headroom for season/quality filters

    for imdb_id, _item in candidates:
        for domain in EZTV_DOMAINS:
            if progress:
                progress({"type": "mirror_attempt", "mirror": domain})
            torrents, status = _fetch_eztv_torrents_for_id(imdb_id, domain, timeout)
            if status == 'ok':
                all_torrents.extend(torrents)
                working_domain = domain
                state.eztv_url = f"https://{domain}/api/get-torrents?imdb_id={imdb_id}"
                any_ok_or_empty = True
                break  # this candidate done; move to next candidate
            if status == 'empty':
                any_ok_or_empty = True
                break  # API authoritative → don't probe more mirrors for this id
            if progress:
                progress({"type": "mirror_failed", "mirror": domain})
        if len(all_torrents) >= target:
            break

    if not all_torrents:
        if any_ok_or_empty:
            # Mirrors responded for at least one candidate but every candidate
            # came back empty → genuine no-results, not a network failure.
            if progress:
                progress({"type": "empty"})
            return []
        if not quiet_mode:
            print(colored.magenta("[EZTV] Error : All known mirrors unreachable or no results"))
        if progress:
            progress({"type": "failed"})
        return []

    parsed = _parse_eztv_json(all_torrents, domain=working_domain, season=season, episode=episode, filters=filters, limit=limit)

    # Merge IMDB suggestion enrichment (cast + series start year) into each
    # row's metadata. Each torrent has its own imdb_id; pick the matching
    # enrichment, if any. IMDB-supplied year overrides per-episode air date
    # for the `released` slot (the suggestion item answers "when did this
    # show start"; the per-episode air date stays available via `uploaded`).
    for row in parsed:
        md = row.get("metadata") or {}
        imdb_code = md.get("imdb_code", "")
        imdb_id_num = imdb_code.removeprefix("tt") if imdb_code else ""
        enrich = imdb_enrichment.get(imdb_id_num)
        if enrich:
            md.update(enrich)
            row["metadata"] = md

    if not parsed and (season or episode or filters) and not quiet_mode:
        filter_desc = ''
        if season:
            filter_desc += f" S{season.zfill(2)}"
        if episode:
            filter_desc += f"E{episode.zfill(2)}"
        if filters:
            filter_desc += f" {' '.join(filters)}"
        print(colored.yellow(f"[EZTV] No results matching{filter_desc} ({len(all_torrents)} total for this show)"))

    if progress:
        if parsed:
            progress({"type": "ok", "count": len(parsed), "mirror": working_domain})
        else:
            progress({"type": "empty"})

    return parsed
