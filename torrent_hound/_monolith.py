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
import os  # noqa: F401  — kept for tests that patch th.os
import socket  # noqa: F401  — kept for tests that patch th.socket
import sys
import time  # noqa: F401  — kept for tests that patch th.time
import urllib.parse  # noqa: F401  — kept for tests that patch th.urllib
import webbrowser  # noqa: F401  — kept for tests that patch th.webbrowser
from concurrent.futures import ThreadPoolExecutor  # noqa: F401
from datetime import datetime, timezone  # noqa: F401
from pathlib import Path  # noqa: F401

if sys.version_info >= (3, 11):
    import tomllib  # noqa: F401
else:
    import tomli as tomllib  # noqa: F401  — backport; same API surface we use

import argcomplete
import platformdirs  # noqa: F401
import pyperclip  # noqa: F401  — kept for tests that patch th.pyperclip
import requests  # noqa: F401  — kept for tests that patch th.requests
import tomli_w  # noqa: F401
from argcomplete.shell_integration import shellcode as _argcomplete_shellcode
from bs4 import BeautifulSoup  # noqa: F401

from torrent_hound import state  # noqa: E402, F401  — exposed as th.state and used by main()

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
from torrent_hound.repl import (  # noqa: E402, F401
    _NUMERIC_CMDS,
    _cmd_c,
    _cmd_cs,
    _cmd_d,
    _cmd_m,
    _cmd_o,
    _get_entry,
    print_menu,
    switch,
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
from torrent_hound.ui import (  # noqa: E402, F401
    _build_results_table,
    colored,
    console,
    convertListJSONToPureJSON,
    pretty_print_top_results_piratebay,
    prettyPrintCombinedTopResults,
    printResultsQuietly,
    printTopResults,
)

# defaultQuery still lives here during the migration; moves to cli.py in Commit 7.
defaultQuery = 'ubuntu'

try:
    from importlib.metadata import version as _pkg_version
    __version__ = _pkg_version("torrent-hound")
except Exception:
    __version__ = "dev"


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
        state.query = ' '.join(args.query)
    else:
        print("Please enter a valid query.")
        sys.exit(0)

    if args.quiet or args.as_json:
        searchAllSites(state.query, quiet_mode=True)
        printResultsQuietly(as_json=args.as_json)
    else:
        searchAllSites(state.query)
        printTopResults()

        state.should_exit = False
        while not state.should_exit:
            print_menu(1)
            choice = input("Enter command : ")
            switch(choice)

if __name__ == '__main__':
    main()
