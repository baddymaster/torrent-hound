"""1337x source — currently dormant.

Cloudflare's managed-challenge layer blocks `requests`-based scraping. This
module is kept so re-enabling the source becomes one line in
`sources/__init__.py._SOURCES` if either:
  - `cloudscraper` ships a version that handles managed challenges, or
  - a maintained public 1337x proxy API appears (non-Playwright, stable)

If you're trying to re-enable: the parser still works on the rendered HTML;
the blocker is purely getting past CF on the first request. The User-Agent
in `extract_magnet_link_1337x` predates the CF rollout and is left for
parity with the old code path. Replace with whatever evades CF when the
landscape changes.
"""

from bs4 import BeautifulSoup

from torrent_hound import state, ui
from torrent_hound.ui import colored

from .base import _https_get, removeAndReplaceSpaces


def extract_magnet_link_1337x(url):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 6.0; WOW64; rv:24.0) Gecko/20100101 Firefox/24.0'}
    response = _https_get(url, headers=headers)
    soup = BeautifulSoup(response.content, 'html.parser')
    magnet_link = soup.find('a', href=lambda href: href and href.startswith("magnet:"))
    if magnet_link:
        return magnet_link['href']
    else:
        return None


def search1337x(search_string='', domain='1337x.to', quiet_mode=False, limit=10, progress=None):  # noqa: ARG001  — keyword reserved for the source-trail callback; dormant source doesn't emit yet
    query = removeAndReplaceSpaces(search_string)
    page_no = 1
    baseURL = f'https://{domain}'
    url = f'{baseURL}/search/{query}/{page_no}/'
    state.url_1337x = url

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 6.0; WOW64; rv:24.0) Gecko/20100101 Firefox/24.0'}
    response = _https_get(url, headers=headers)
    results = []

    if response.status_code == 403 and response.headers.get('cf-mitigated', '').lower() == 'challenge':
        if not quiet_mode:
            print(colored.magenta("[1337x] Error : Blocked by Cloudflare captcha"))
        state.results_1337x = results
        return results

    soup = BeautifulSoup(response.text, 'html.parser')

    try:
        table = soup.find('table', {'class': 'table-list'})
        rows = table.tbody.find_all('tr')
        for row in rows[:limit]:
            row_data = {}
            name_col = row.find('td', {'class': 'coll-1 name'})
            row_data['name'] = name_col.a.next_sibling.text
            row_data['link'] = baseURL + name_col.a.next_sibling['href']
            row_data['seeders'] = int(row.find('td', {'class': 'coll-2 seeds'}).text.strip())
            row_data['leechers'] = int(row.find('td', {'class': 'coll-3 leeches'}).text.strip())
            try:
                row_data['ratio'] = format( (float(row_data['seeders'])/float(row_data['leechers'])), '.1f' )
            except ZeroDivisionError:
                row_data['ratio'] = 'inf'
            row_data['time'] = row.find('td', {'class': 'coll-date'}).text.strip()
            size_col = row.find('td', {'class': 'coll-4'})
            if size_col:
                row_data['size'] = size_col.contents[0].strip()
            else:
                row_data['size'] = ''
            row_data['magnet'] = extract_magnet_link_1337x(row_data['link'])
            results.append(row_data)
    except AttributeError:
        if not quiet_mode:
            print(colored.magenta("[1337x] Error : No results found"))
    state.results_1337x = results
    return results


def pretty_print_top_results_1337x(limit=10):
    table, count = ui._build_results_table(state.results_1337x, "1337x", start_index=state.num_results + 1, limit=limit)
    ui.console.print(table)
    return state.num_results + count
