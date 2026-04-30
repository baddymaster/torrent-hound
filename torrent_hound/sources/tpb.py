"""The Pirate Bay source: multi-domain fallback + HTML parser."""

import re

import requests
from bs4 import BeautifulSoup

from torrent_hound import state
from torrent_hound.ui import colored

from .base import _extract_release_tags, removeAndReplaceSpaces

_DEFAULT_QUERY = 'ubuntu'

# `Movie.Title.2024.1080p` or `Movie Title (2024) [...]` — pull the
# rightmost 19xx/20xx so episode-numeric tokens (e.g. `1984`) don't
# false-match for content that's actually from a different decade.
_YEAR_RE = re.compile(r'\b(19\d{2}|20\d{2})\b')

# TPB domains tried in order. Mirrors churn often; add new ones to the front
# when they come up, drop dead ones from the tail.
TPB_DOMAINS = [
    'thepiratebay.zone',
    'thepiratebay.org',
    'tpb.party',
    'piratebay.party',
    'pirateproxy.live',
]


def _tpb_page_is_empty_results(html) -> bool:
    """True if `html` is a successfully-served TPB results page that just has
    zero matches (the searchResult table is present but contains only the
    header row). Distinguishes from dead/blocked mirrors so the source can
    emit `empty` (genuine no-results, stop probing) vs `mirror_failed`
    (table missing, try the next mirror)."""
    soup = BeautifulSoup(html, 'html.parser')
    table = soup.find("table", {"id": "searchResult"})
    if table is None:
        return False
    return len(table.find_all("tr")) <= 1


def _parse_tpb_html(html, domain='thepiratebay.zone', limit=10):
    """Parse a TPB search-results HTML document. Returns [] if the expected
    results table isn't present (domain is dead / blocked / CAPTCHA)."""
    soup = BeautifulSoup(html, 'html.parser')
    table = soup.find("table", {"id": "searchResult"})
    if table is None:
        return []
    trs = table.find_all("tr")[1:]  # drop header row
    parsed = []
    base = f'https://{domain}'
    for tr in trs[:limit]:
        tds = tr.find_all("td")
        try:
            link_name = tds[1].find("a", {"class": "detLink"})
            href = link_name["href"]
            link = href if href.startswith("http") else f"{base}{href}"
            res = {
                'name': link_name.contents[0].strip(),
                'link': link,
                'seeders': int(tds[2].contents[0]),
                'leechers': int(tds[3].contents[0]),
                'magnet': tds[1].find("img", {"alt": "Magnet link"}).parent['href'],
                'size': str(tds[1].find("font").contents[0].split(',')[1].split(' ')[2].replace('\xa0', ' ')),
            }
            try:
                res['ratio'] = format(float(res['seeders']) / float(res['leechers']), '.1f')
            except ZeroDivisionError:
                res['ratio'] = 'inf'
            metadata: dict = {"name": res["name"]}
            metadata.update(_extract_release_tags(res["name"]))
            year_matches = _YEAR_RE.findall(res["name"])
            if year_matches:
                metadata["released"] = year_matches[-1]
            res['metadata'] = metadata
            parsed.append(res)
        except (AttributeError, IndexError, KeyError):
            continue  # malformed row; skip
    return parsed


def searchPirateBayCondensed(search_string=None, quiet_mode=False, limit=10, timeout=8, progress=None):
    """Search TPB, trying known mirrors in order until one returns results.
    On success, remembers the working domain for subsequent calls in this run.

    `progress`, if provided, receives `mirror_attempt`/`mirror_failed`/`ok`/
    `failed` events for the TUI's source-trail display.
    """
    if search_string is None:
        search_string = _DEFAULT_QUERY

    # Try last-known-good domain first, then the rest
    domains_to_try = [state.tpb_working_domain] + [d for d in TPB_DOMAINS if d != state.tpb_working_domain]
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 6.0; WOW64; rv:24.0) Gecko/20100101 Firefox/24.0'}

    for domain in domains_to_try:
        url = f'https://{domain}/s/?q={removeAndReplaceSpaces(search_string)}&page=0&orderby=99'
        if progress:
            progress({"type": "mirror_attempt", "mirror": domain})
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            parsed = _parse_tpb_html(r.content, domain=domain, limit=limit)
            if parsed:
                state.tpb_working_domain = domain
                state.tpb_url = url
                state.results_tpb_condensed = parsed
                if progress:
                    progress({"type": "ok", "count": len(parsed), "mirror": domain})
                return parsed
            # Empty parse: distinguish "mirror served us a real no-hits page"
            # from "mirror is dead / blocked / CAPTCHA". Probing more mirrors
            # only makes sense for the latter.
            if _tpb_page_is_empty_results(r.content):
                state.tpb_working_domain = domain
                state.results_tpb_condensed = []
                if progress:
                    progress({"type": "empty"})
                return []
            if progress:
                progress({"type": "mirror_failed", "mirror": domain})
        except requests.RequestException:
            if progress:
                progress({"type": "mirror_failed", "mirror": domain})
            continue

    if not quiet_mode:
        print(colored.magenta("[PirateBay] Error : All known mirrors returned no results or were unreachable"))
    state.results_tpb_condensed = []
    if progress:
        progress({"type": "failed"})
    return state.results_tpb_condensed
