#!/usr/bin/env python3
# @author : Yashovardhan Sharma
# @github : github.com/baddymaster

#   <Torrent Hound - Search torrents from multiple websites via the CLI.>
#    Copyright (C) <2017-2026>  <Yashovardhan Sharma>
#
#     This program is free software: you can redistribute it and/or modify
#     it under the terms of the GNU Affero General Public License as published
#     by the Free Software Foundation, either version 3 of the License, or
#     (at your option) any later version.
#
#     This program is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU Affero General Public License for more details.
#
#     You should have received a copy of the GNU Affero General Public License
#     along with this program.  If not, see <http://www.gnu.org/licenses/>.

import argparse
import json
import re
import sys
import webbrowser
from concurrent.futures import ThreadPoolExecutor

import pyperclip
import requests
from bs4 import BeautifulSoup
from rich.console import Console
from rich.table import Table

__version__ = "2.2.0"

console = Console()

class colored:
    """Minimal ANSI color wrapper so colored.<name>(s) calls still produce
    escape-coded strings usable with plain print()."""
    @staticmethod
    def red(s): return f"\x1b[31m{s}\x1b[0m"
    @staticmethod
    def green(s): return f"\x1b[32m{s}\x1b[0m"
    @staticmethod
    def yellow(s): return f"\x1b[33m{s}\x1b[0m"
    @staticmethod
    def blue(s): return f"\x1b[34m{s}\x1b[0m"
    @staticmethod
    def magenta(s): return f"\x1b[35m{s}\x1b[0m"

defaultQuery, query = 'ubuntu', ''
results_tpb_condensed = None
results_1337x = None
results, results_rarbg, exit = None, None, None
num_results = 0
tpb_working_domain = 'thepiratebay.zone'
tpb_url, url_1337x = '', ''

def extract_magnet_link_1337x(url):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 6.0; WOW64; rv:24.0) Gecko/20100101 Firefox/24.0'}
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.content, 'html.parser')
    magnet_link = soup.find('a', href=lambda href: href and href.startswith("magnet:"))
    if magnet_link:
        return magnet_link['href']
    else:
        return None

def search1337x(search_string=defaultQuery, domain='1337x.to', quiet_mode=False, limit=10):
    global results_1337x, url_1337x

    query = removeAndReplaceSpaces(search_string)
    page_no = 1
    baseURL = f'https://{domain}'
    url = f'{baseURL}/search/{query}/{page_no}/'
    url_1337x = url

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 6.0; WOW64; rv:24.0) Gecko/20100101 Firefox/24.0'}
    response = requests.get(url, headers=headers)
    results_1337x = []

    if response.status_code == 403 and response.headers.get('cf-mitigated', '').lower() == 'challenge':
        if not quiet_mode:
            print(colored.magenta("[1337x] Error : Blocked by Cloudflare captcha"))
        return results_1337x

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
            # uploader_col = row.find('td', {'class': 'coll-5'})
            # if uploader_col:
            #     row_data['uploader'] = uploader_col.contents[0].text.strip()
            # else:
            #     row_data['uploader'] = ''
            row_data['magnet'] = extract_magnet_link_1337x(row_data['link'])
            results_1337x.append(row_data)
    except AttributeError:
        if not quiet_mode:
            print(colored.magenta("[1337x] Error : No results found"))
    return results_1337x

def pretty_print_top_results_1337x(limit=10):
    global results_1337x, num_results
    table, count = _build_results_table(results_1337x, "1337x", start_index=num_results + 1, limit=limit)
    console.print(table)
    return num_results + count

def removeAndReplaceSpaces(string):
    if string[0] == " ":
        string = string[1:]
    return string.replace(" ", "+")

# TPB domains tried in order. Mirrors churn often; add new ones to the front
# when they come up, drop dead ones from the tail.
TPB_DOMAINS = [
    'thepiratebay.zone',
    'thepiratebay.org',
    'tpb.party',
    'piratebay.party',
    'pirateproxy.live',
]

def _parse_tpb_html(html, limit=10):
    """Parse a TPB search-results HTML document. Returns [] if the expected
    results table isn't present (domain is dead / blocked / CAPTCHA)."""
    soup = BeautifulSoup(html, 'html.parser')
    table = soup.find("table", {"id": "searchResult"})
    if table is None:
        return []
    trs = table.find_all("tr")[1:]  # drop header row
    parsed = []
    for tr in trs[:limit]:
        tds = tr.find_all("td")
        try:
            link_name = tds[1].find("a", {"class": "detLink"})
            res = {
                'name': link_name.contents[0].strip(),
                'link': link_name["href"],
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

def searchPirateBayCondensed(search_string=defaultQuery, quiet_mode=False, limit=10, timeout=8):
    """Search TPB, trying known mirrors in order until one returns results.
    On success, remembers the working domain for subsequent calls in this run."""
    global tpb_working_domain, tpb_url, results_tpb_condensed

    # Try last-known-good domain first, then the rest
    domains_to_try = [tpb_working_domain] + [d for d in TPB_DOMAINS if d != tpb_working_domain]
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 6.0; WOW64; rv:24.0) Gecko/20100101 Firefox/24.0'}

    for domain in domains_to_try:
        url = f'https://{domain}/s/?q={removeAndReplaceSpaces(search_string)}&page=0&orderby=99'
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            parsed = _parse_tpb_html(r.content, limit=limit)
            if parsed:
                tpb_working_domain = domain
                tpb_url = url
                results_tpb_condensed = parsed
                return parsed
        except requests.RequestException:
            continue  # try next mirror

    if not quiet_mode:
        print(colored.magenta("[PirateBay] Error : All known mirrors returned no results or were unreachable"))
    results_tpb_condensed = []
    return results_tpb_condensed

def _build_results_table(entries, source_name, start_index=1, limit=10):
    """Build a rich Table from a list of result dicts. Returns (table, count_added)."""
    table = Table(
        title=f"[green]{source_name}[/green]",
        header_style="red",
        padding=(0, 1),
        show_lines=False,
    )
    table.add_column("No", justify="left")
    table.add_column("Torrent Name", justify="left", no_wrap=True)
    table.add_column("Size", justify="right")
    table.add_column("S", justify="right")
    table.add_column("L", justify="right")
    table.add_column("S/L", justify="right")

    if entries and entries != [{}]:
        index = start_index
        for r in entries[:limit]:
            if not r:
                continue
            try:
                table.add_row(
                    str(index),
                    r['name'][:57],
                    r['size'],
                    str(r['seeders']),
                    str(r['leechers']),
                    str(r['ratio']),
                )
                index += 1
            except KeyError as e:
                console.print(f"[yellow]Skipping malformed row: {e}[/yellow]")
        return table, index - start_index
    table.add_row("Null", "Null", "Null", "Null", "Null", "Null")
    return table, 0

def pretty_print_top_results_piratebay(limit=10):
    global results
    table, count = _build_results_table(results, "PirateBay", start_index=1, limit=limit)
    console.print(table)
    return count

def _get_entry(resNum):
    """Return the search result dict for a 1-indexed result number, or None if invalid."""
    if resNum <= 0 or resNum > num_results:
        return None
    return results[resNum - 1]

# Commands that take a numeric argument and their handlers. Each handler
# receives the result entry (dict with 'magnet' and 'link' keys).
def _cmd_m(entry):
    print("\nMagnet Link : \n" + entry['magnet'])

def _cmd_c(entry):
    pyperclip.copy(str(entry['magnet']))
    print('Magnet link copied to clipboard!')

def _cmd_cs(entry):
    pyperclip.copy(str(entry['magnet']))
    webbrowser.open('https://www.seedr.cc', new=2)
    print('Seedr.cc opened and Magnet link copied to clipboard!')

def _cmd_d(entry):
    webbrowser.open(entry['magnet'], new=2)
    print('Magnet link sent to default torrent client!')

def _cmd_o(entry):
    webbrowser.open(entry['link'], new=2)
    print('Torrent page opened in default browser!')

# Longer prefixes must come first so 'cs' matches before 'c'.
_NUMERIC_CMDS = [('cs', _cmd_cs), ('c', _cmd_c), ('m', _cmd_m), ('d', _cmd_d), ('o', _cmd_o)]

def switch(arg):
    global exit, query

    # Numeric commands: m<n>, c<n>, cs<n>, d<n>, o<n>
    for prefix, handler in _NUMERIC_CMDS:
        match = re.match(rf'^{prefix}(\d+)$', arg)
        if match:
            entry = _get_entry(int(match.group(1)))
            if entry is None:
                print('Invalid command!\n')
            else:
                handler(entry)
            return

    # Commands with no argument
    if arg == 'u':
        print(colored.green('[PirateBay] URL') + ' : ' + tpb_url)
    elif arg == 'h':
        print_menu(0)
    elif arg == 'q':
        exit = True
    elif arg == 'p':
        printTopResults()
    elif arg == 's':
        query = input("Enter query : ")
        if query == '':
            query = defaultQuery
        searchAllSites(query, force_search=True)
        printTopResults()
    elif arg == 'r':
        searchAllSites(query)
        printTopResults()
    else:
        print('Invalid command!\n')

def print_menu(arg=0):
    if arg == 0:
        print('''
        ------ Help Menu -------
        Available Commands :
        1. m<result number> - Print magnet link of selected torrent
        2. c<result number> - Copy magnet link of selected torrent to clipboard
        3. d<result number> - Download torrent using default torrent client
        4. o<result number> - Open the torrent page of the selected torrent in the default browser
        5. cs<result number> - Copy magnet link and open seedr.cc
        6. p - Re-print top 10 results for the last search
        7. s - Enter a new query to search for over all available torrent websites
        8. r - Repeat last search (with same query)
        ------------------------''')
    elif arg == 1:
        print('''
        Enter 'q' to exit and 'h' to see all available commands.
        ''')

# Registry of active torrent sources. Each entry is (display_name, callable).
# The callable takes (query, quiet_mode) and returns a list of result dicts.
# To re-enable 1337x: uncomment its entry (and see search1337x for CF caveats).
_SOURCES = [
    ('TPB', lambda q, qm: searchPirateBayCondensed(search_string=q, quiet_mode=qm)),
    # ('1337x', lambda q, qm: search1337x(q, quiet_mode=qm)),
]

def searchAllSites(query=defaultQuery, force_search=False, quiet_mode=False):
    global results, results_rarbg, results_tpb_condensed, results_1337x

    if force_search:
        results_1337x = None
        results = None
        results_tpb_condensed = None

    # RARBG and SkyTorrents permanently removed. See git history.
    results_rarbg = []

    if not quiet_mode:
        names = ", ".join(name for name, _ in _SOURCES)
        print(colored.magenta(f"Searching {names}..."), end='')

    # Fan out all source searches in parallel. With one source this is a no-op;
    # with N sources, total latency drops to max() instead of sum().
    with ThreadPoolExecutor(max_workers=max(1, len(_SOURCES))) as pool:
        futures = {name: pool.submit(fn, query, quiet_mode) for name, fn in _SOURCES}
        source_results = {name: (fut.result() or []) for name, fut in futures.items()}

    if not quiet_mode:
        print(colored.green("Done."))

    results_tpb_condensed = source_results.get('TPB', [])
    results = results_tpb_condensed
    results_1337x = source_results.get('1337x', [])

def prettyPrintCombinedTopResults():
    global num_results
    num_results = pretty_print_top_results_piratebay(10)

def printTopResults():
    prettyPrintCombinedTopResults()

def convertListJSONToPureJSON(result_list):
    # Sample JSON Structure
    # {
    #  'count' : x,    ### Gives total number of results
    #  'results' : {'0' : {...}, {'1' : {...}, ...}   ### Stores actual results
    # }
    result_json = {'count' : '0'}
    index = 0

    if result_list != [] and result_list is not None: # Create a key 'results' only if there are some results
        result_json['results'] = {}
        rj_results = result_json['results']

        for _ in result_list:
            rj_results[str(index)] = result_list[index]
            index += 1
        result_json['count'] = str(index) # Update total number of results

    return result_json

def printResultsQuietly(as_json=False):
    global results_rarbg, results_tpb_condensed, results_1337x

    combined_json_results = {
        'rarbg': convertListJSONToPureJSON(results_rarbg),
        'tpb': convertListJSONToPureJSON(results_tpb_condensed),
        '1337x': convertListJSONToPureJSON(results_1337x),
    }

    if as_json:
        print(json.dumps(combined_json_results))
    else:
        print(combined_json_results)

def main():
    global query, exit

    parser = argparse.ArgumentParser(prog="torrent-hound")
    parser.add_argument("query", help="Specify the search query", nargs='+', default=defaultQuery)
    parser.add_argument('-q', '--quiet', help='Print output of search without any additional options', default=False, action='store_true')
    parser.add_argument('--json', help='Print results as JSON (implies --quiet)', default=False, action='store_true', dest='as_json')
    parser.add_argument('-V', '--version', action='version', version=f'%(prog)s {__version__}')

    args = parser.parse_args()

    if args.query:
        query = ' '.join(args.query)
    else:
        print("Please enter a valid query.")
        sys.exit(0)

    if args.quiet or args.as_json:
        searchAllSites(query, quiet_mode=True)
        printResultsQuietly(as_json=args.as_json)
    else:
        searchAllSites(query)
        printTopResults()

        exit = False
        while not exit:
            print_menu(1)
            choice = input("Enter command : ")
            switch(choice)

if __name__ == '__main__':
    main()
