"""The Pirate Bay source: multi-domain fallback + HTML parser."""
from __future__ import annotations

import requests
from bs4 import BeautifulSoup

from torrent_hound import state
from torrent_hound.ui import colored

from .base import removeAndReplaceSpaces

_DEFAULT_QUERY = 'ubuntu'

# TPB domains tried in order. Mirrors churn often; add new ones to the front
# when they come up, drop dead ones from the tail.
TPB_DOMAINS = [
    'thepiratebay.zone',
    'thepiratebay.org',
    'tpb.party',
    'piratebay.party',
    'pirateproxy.live',
]


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
            parsed.append(res)
        except (AttributeError, IndexError, KeyError):
            continue  # malformed row; skip
    return parsed


def searchPirateBayCondensed(search_string=None, quiet_mode=False, limit=10, timeout=8):
    """Search TPB, trying known mirrors in order until one returns results.
    On success, remembers the working domain for subsequent calls in this run."""
    if search_string is None:
        search_string = _DEFAULT_QUERY

    # Try last-known-good domain first, then the rest
    domains_to_try = [state.tpb_working_domain] + [d for d in TPB_DOMAINS if d != state.tpb_working_domain]
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 6.0; WOW64; rv:24.0) Gecko/20100101 Firefox/24.0'}

    for domain in domains_to_try:
        url = f'https://{domain}/s/?q={removeAndReplaceSpaces(search_string)}&page=0&orderby=99'
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            parsed = _parse_tpb_html(r.content, domain=domain, limit=limit)
            if parsed:
                state.tpb_working_domain = domain
                state.tpb_url = url
                state.results_tpb_condensed = parsed
                return parsed
        except requests.RequestException:
            continue  # try next mirror

    if not quiet_mode:
        print(colored.magenta("[PirateBay] Error : All known mirrors returned no results or were unreachable"))
    state.results_tpb_condensed = []
    return state.results_tpb_condensed
