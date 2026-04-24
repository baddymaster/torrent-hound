#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK
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
import base64  # noqa: F401  — kept for tests that patch th.base64
import getpass  # noqa: F401  — kept for tests that patch th.getpass
import json
import os  # noqa: F401  — kept for tests that patch th.os
import re
import socket  # noqa: F401  — kept for tests that patch th.socket
import sys
import time  # noqa: F401  — kept for tests that patch th.time
import urllib.parse  # noqa: F401  — kept for tests that patch th.urllib
import webbrowser
from concurrent.futures import ThreadPoolExecutor  # noqa: F401
from datetime import datetime, timezone  # noqa: F401
from pathlib import Path  # noqa: F401

if sys.version_info >= (3, 11):
    import tomllib  # noqa: F401
else:
    import tomli as tomllib  # noqa: F401  — backport; same API surface we use

import argcomplete
import platformdirs  # noqa: F401
import pyperclip
import requests  # noqa: F401  — kept for tests that patch th.requests
import tomli_w  # noqa: F401
from argcomplete.shell_integration import shellcode as _argcomplete_shellcode
from bs4 import BeautifulSoup  # noqa: F401
from rich.console import Console
from rich.table import Table

# Re-import extracted-package names so callers inside this module (still the
# bulk of the codebase during the migration) can reference them unqualified.
# Each subsequent commit of the package split adds another line here.
from torrent_hound.cache import (  # noqa: E402, F401
    _CACHE_TTL_SECONDS,
    _RESULT_CACHE,
    _cache_get,
    _cache_put,
    _format_age,
    _normalize_query,
    _print_cache_feedback,
)
from torrent_hound.config import (  # noqa: E402, F401
    _RD_ACTION_DESCRIPTIONS,
    _RD_VALID_ACTIONS,
    _config_path,
    _configure_rd,
    _load_config,
    _print_config_path,
    _prompt_rd_action,
    _prompt_rd_token,
    _resolve_rd_action,
    _resolve_rd_token,
    _revoke_rd_token,
    _save_config,
    _user_status,
)
from torrent_hound.realdebrid import (  # noqa: E402, F401
    _ANSI_ESCAPE_RE,
    _RD_API,
    _RD_ERROR_MESSAGES,
    _RD_HASH_RE,
    _cmd_rd,
    _human_size,
    _rd_add_magnet,
    _rd_apply_action,
    _rd_check_cached,
    _rd_get_info,
    _rd_has_cdn_markers,
    _rd_parse_error_body,
    _rd_parse_hash,
    _rd_parse_selection,
    _rd_prompt_file_selection,
    _rd_request,
    _rd_select_files,
    _rd_unrestrict,
    _RdError,
    _strip_ansi,
)
from torrent_hound.sources import _SOURCES, searchAllSites  # noqa: E402, F401
from torrent_hound.sources.base import _format_bytes, removeAndReplaceSpaces  # noqa: E402, F401
from torrent_hound.sources.eztv import (  # noqa: E402, F401
    EZTV_DOMAINS,
    _eztv_slug,
    _imdb_lookup,
    _parse_episode_query,
    _parse_eztv_json,
    searchEZTV,
)
from torrent_hound.sources.legacy_1337x import (  # noqa: E402, F401
    extract_magnet_link_1337x,
    pretty_print_top_results_1337x,
    search1337x,
)
from torrent_hound.sources.tpb import (  # noqa: E402, F401
    TPB_DOMAINS,
    _parse_tpb_html,
    searchPirateBayCondensed,
)
from torrent_hound.sources.yts import (  # noqa: E402, F401
    YTS_DOMAINS,
    YTS_TRACKERS,
    _build_yts_magnet,
    _parse_yts_json,
    searchYTS,
)

try:
    from importlib.metadata import version as _pkg_version
    __version__ = _pkg_version("torrent-hound")
except Exception:
    __version__ = "dev"

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
results_yts = None
results_eztv = None
results, results_rarbg, exit = None, None, None
num_results = 0
tpb_working_domain = 'thepiratebay.zone'
tpb_url, yts_url, eztv_url, url_1337x = '', '', '', ''



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
                    re.sub(r'[^\x20-\x7E]', '', r['name'])[:57],
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

# Longer prefixes must come first so 'cs' matches before 'c', and 'rd' before any
# future 'r<n>' command. Dispatch tests observe side effects (e.g. the printed
# "token not configured" message from _cmd_rd) rather than patching handlers.
_NUMERIC_CMDS = [
    ('rd', _cmd_rd),
    ('cs', _cmd_cs),
    ('c', _cmd_c),
    ('m', _cmd_m),
    ('d', _cmd_d),
    ('o', _cmd_o),
]

def switch(arg):
    global exit, query

    # Numeric commands: m<n>, c<n>, cs<n>, d<n>, o<n>, rd<n>
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
        if tpb_url:
            print(colored.green('[PirateBay] URL') + ' : ' + tpb_url)
        if yts_url:
            print(colored.green('[YTS] URL') + ' : ' + yts_url)
        if eztv_url:
            print(colored.green('[EZTV] URL') + ' : ' + eztv_url)
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
        searchAllSites(query)
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
        6. rd<result number> - Debrid and download via Real-Debrid (requires token)
        7. p - Re-print top 10 results for the last search
        8. s - Enter a new query (5-min cache reused when available)
        9. r - Repeat last search (cached sources reused; failed sources retry)
        ------------------------''')
    elif arg == 1:
        print('''
        Enter 'q' to exit and 'h' to see all available commands.
        ''')


def prettyPrintCombinedTopResults():
    global num_results
    num_results = pretty_print_top_results_piratebay(10)
    if results_yts:
        table, count = _build_results_table(results_yts, "YTS", start_index=num_results + 1, limit=10)
        console.print(table)
        num_results += count
    if results_eztv:
        table, count = _build_results_table(results_eztv, "EZTV", start_index=num_results + 1, limit=10)
        console.print(table)
        num_results += count

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
    global results_rarbg, results_tpb_condensed, results_1337x, results_yts, results_eztv

    combined_json_results = {
        'rarbg': convertListJSONToPureJSON(results_rarbg),
        'tpb': convertListJSONToPureJSON(results_tpb_condensed),
        'yts': convertListJSONToPureJSON(results_yts),
        'eztv': convertListJSONToPureJSON(results_eztv),
        '1337x': convertListJSONToPureJSON(results_1337x),
    }

    if as_json:
        print(json.dumps(combined_json_results))
    else:
        print(combined_json_results)

def _build_parser():
    parser = argparse.ArgumentParser(prog="torrent-hound")
    parser.add_argument("query", help="Specify the search query", nargs='*', default=[])
    parser.add_argument('-q', '--quiet', help='Print output of search without any additional options', default=False, action='store_true')
    parser.add_argument('--json', help='Print results as JSON (implies --quiet)', default=False, action='store_true', dest='as_json')
    parser.add_argument('-V', '--version', action='version', version=f'%(prog)s {__version__}')
    parser.add_argument('--configure-rd', help='Interactively set up Real-Debrid token and action', default=False, action='store_true', dest='configure_rd')
    parser.add_argument('--config-path', help='Print the resolved config file path and exit', default=False, action='store_true', dest='config_path')
    parser.add_argument('--user-status', help='Show RD account info (token validity, premium expiration, points) and exit', default=False, action='store_true', dest='user_status')
    parser.add_argument('--revoke-rd-token', help='Invalidate the current RD token on Real-Debrid and optionally remove it from config', default=False, action='store_true', dest='revoke_rd_token')
    parser.add_argument('--print-completion', help='Print shell completion code for the given shell (bash or zsh) and exit', choices=['bash', 'zsh'], default=None, dest='print_completion')
    return parser


def main():
    global query, exit

    parser = _build_parser()
    argcomplete.autocomplete(parser)
    args = parser.parse_args()

    if args.print_completion:
        print(_argcomplete_shellcode(['torrent-hound'], shell=args.print_completion))
        sys.exit(0)
    if args.config_path:
        sys.exit(_print_config_path())
    if args.configure_rd:
        sys.exit(_configure_rd())
    if args.user_status:
        sys.exit(_user_status())
    if args.revoke_rd_token:
        sys.exit(_revoke_rd_token())

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
