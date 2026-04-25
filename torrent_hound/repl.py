"""Interactive REPL: numeric-prefixed commands (m1, c2, rd3, ...) plus
single-letter commands (u, h, q, p, s, r). Reads/writes shared state in
`torrent_hound.state` and dispatches to the per-command handlers.

`_cmd_rd` for Real-Debrid lives in `torrent_hound.realdebrid` (it's a thin
wrapper over the RD helpers); imported here so `_NUMERIC_CMDS` can include it.
"""
from __future__ import annotations

import re
import webbrowser

import pyperclip

from torrent_hound import state, ui
from torrent_hound.realdebrid import _cmd_rd

_DEFAULT_QUERY = 'ubuntu'


def _get_entry(resNum):
    """Return the search result dict for a 1-indexed result number, or None if invalid."""
    if resNum <= 0 or resNum > state.num_results:
        return None
    return state.results[resNum - 1]


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
    # Lazy import: searchAllSites lives in sources/__init__ which depends on
    # this module indirectly. Import-at-call-time keeps the import graph clean.
    from torrent_hound.sources import searchAllSites

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
        if state.tpb_url:
            print(ui.colored.green('[PirateBay] URL') + ' : ' + state.tpb_url)
        if state.yts_url:
            print(ui.colored.green('[YTS] URL') + ' : ' + state.yts_url)
        if state.eztv_url:
            print(ui.colored.green('[EZTV] URL') + ' : ' + state.eztv_url)
    elif arg == 'h':
        print_menu(0)
    elif arg == 'q':
        state.should_exit = True
    elif arg == 'p':
        ui.printTopResults()
    elif arg == 's':
        state.query = input("Enter query : ")
        if state.query == '':
            state.query = _DEFAULT_QUERY
        searchAllSites(state.query)
        ui.printTopResults()
    elif arg == 'r':
        searchAllSites(state.query)
        ui.printTopResults()
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
