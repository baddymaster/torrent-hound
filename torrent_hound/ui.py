"""Rendering primitives: rich Console singleton, ANSI color shim,
results-table builder, quiet/JSON output formatters.

Reads state from `torrent_hound.state` for the cross-source aggregation
helpers. No state writes here — UI is read-only against the cache /
search results that `sources.searchAllSites` populates.
"""
from __future__ import annotations

import json
import re

from rich.console import Console
from rich.table import Table

from torrent_hound import state

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
    table, count = _build_results_table(state.results, "PirateBay", start_index=1, limit=limit)
    console.print(table)
    return count


def prettyPrintCombinedTopResults():
    state.num_results = pretty_print_top_results_piratebay(10)
    if state.results_yts:
        table, count = _build_results_table(state.results_yts, "YTS", start_index=state.num_results + 1, limit=10)
        console.print(table)
        state.num_results += count
    if state.results_eztv:
        table, count = _build_results_table(state.results_eztv, "EZTV", start_index=state.num_results + 1, limit=10)
        console.print(table)
        state.num_results += count


def printTopResults():
    prettyPrintCombinedTopResults()


def convertListJSONToPureJSON(result_list):
    # Sample JSON Structure
    # {
    #  'count' : x,    ### Gives total number of results
    #  'results' : {'0' : {...}, {'1' : {...}, ...}   ### Stores actual results
    # }
    result_json = {'count': '0'}
    index = 0

    if result_list != [] and result_list is not None:
        result_json['results'] = {}
        rj_results = result_json['results']

        for _ in result_list:
            rj_results[str(index)] = result_list[index]
            index += 1
        result_json['count'] = str(index)

    return result_json


def printResultsQuietly(as_json=False):
    combined_json_results = {
        'rarbg': convertListJSONToPureJSON(state.results_rarbg),
        'tpb':   convertListJSONToPureJSON(state.results_tpb_condensed),
        'yts':   convertListJSONToPureJSON(state.results_yts),
        'eztv':  convertListJSONToPureJSON(state.results_eztv),
        '1337x': convertListJSONToPureJSON(state.results_1337x),
    }

    if as_json:
        print(json.dumps(combined_json_results))
    else:
        print(combined_json_results)
