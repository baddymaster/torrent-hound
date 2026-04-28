"""EZTV source: TV shows via IMDB ID bridge, JSON API, episode/quality filtering."""
from __future__ import annotations

import re

import requests

from torrent_hound import state
from torrent_hound.ui import colored

from .base import _format_bytes

EZTV_DOMAINS = ['eztvx.to', 'eztv.re', 'eztv.wf', 'eztv.it']


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


def _imdb_lookup(query, timeout=8):
    """Look up a TV series IMDB ID via IMDB's public suggestion endpoint.
    Returns the numeric ID string (without 'tt' prefix) or None."""
    slug = query.strip().replace(' ', '_').lower()
    if not slug:
        return None
    url = f'https://v2.sg.media-imdb.com/suggestion/{slug[0]}/{slug}.json'
    try:
        r = requests.get(url, timeout=timeout)
        for item in r.json().get('d', []):
            if item.get('qid') == 'tvSeries':
                return item['id'].removeprefix('tt')
    except (requests.RequestException, ValueError, KeyError):
        pass
    return None


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
        parsed.append({
            'name': title,
            'link': f"https://{domain}/ep/{t.get('id', '')}/{_eztv_slug(title)}/",
            'seeders': seeds,
            'leechers': peers,
            'size': _format_bytes(size_bytes),
            'ratio': ratio,
            'magnet': t.get('magnet_url', ''),
        })
        if len(parsed) >= limit:
            break
    return parsed


def searchEZTV(search_string='', quiet_mode=False, limit=10, timeout=8, progress=None):
    """Search EZTV for TV shows via IMDB ID bridge + optional episode/quality filtering."""
    clean_query, season, episode, filters = _parse_episode_query(search_string)

    imdb_id = _imdb_lookup(clean_query, timeout=timeout)
    if not imdb_id:
        if not quiet_mode:
            print(colored.magenta("[EZTV] No matching TV show found on IMDB"))
        if progress:
            progress({"type": "empty"})
        return []

    # Fetch from EZTV, paginating if needed, with domain fallback
    all_torrents = []
    working_domain = EZTV_DOMAINS[0]
    for domain in EZTV_DOMAINS:
        if progress:
            progress({"type": "mirror_attempt", "mirror": domain})
        try:
            for page in range(1, 4):  # up to 300 episodes
                url = f"https://{domain}/api/get-torrents?imdb_id={imdb_id}&limit=100&page={page}"
                r = requests.get(url, timeout=timeout)
                data = r.json()
                page_torrents = data.get('torrents', [])
                if not page_torrents:
                    break
                all_torrents.extend(page_torrents)
                if len(all_torrents) >= data.get('torrents_count', 0):
                    break
            if all_torrents:
                working_domain = domain
                state.eztv_url = f"https://{domain}/api/get-torrents?imdb_id={imdb_id}"
                break
            # Mirror responded but no torrents — treat as miss and try next.
            if progress:
                progress({"type": "mirror_failed", "mirror": domain})
        except (requests.RequestException, ValueError):
            all_torrents = []
            if progress:
                progress({"type": "mirror_failed", "mirror": domain})
            continue

    if not all_torrents:
        if not quiet_mode:
            print(colored.magenta("[EZTV] Error : All known mirrors unreachable or no results"))
        if progress:
            progress({"type": "failed"})
        return []

    parsed = _parse_eztv_json(all_torrents, domain=working_domain, season=season, episode=episode, filters=filters, limit=limit)

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
