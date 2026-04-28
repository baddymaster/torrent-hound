"""Top-level CLI: argparse wiring, flag dispatch, TUI handoff."""

import argparse
import sys

import argcomplete
from argcomplete.shell_integration import shellcode as _argcomplete_shellcode

from torrent_hound import state
from torrent_hound.config import (
    _configure_rd,
    _print_config_path,
    _revoke_rd_token,
    _user_status,
)
from torrent_hound.sources import searchAllSites
from torrent_hound.ui import printResultsQuietly

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
        # Interactive mode: hand off to the TUI. Search, results display,
        # and the action loop all live inside run_app() now.
        from torrent_hound.tui import run_app
        run_app()
