"""Shared mutable state. One module owns it; readers/writers touch it as
`from torrent_hound import state; state.results = ...` to avoid `global`
declarations scattered across the codebase.

Read by: ui.printResultsQuietly, sources.searchAllSites (writes), tui
(reads via _state.results), realdebrid (entry dicts include source tag).

Conventions:
* Source-specific result lists (`results_*`) are populated by searchAllSites
  in source-of-truth fashion. The flat `results` is their concatenation.
* `should_exit` is set by the `q` key path; checked by the main loop.
* Per-session URLs (`tpb_url` etc.) are diagnostic — last URL fetched per
  source. Not part of the user-facing result data.
"""
from __future__ import annotations

# Populated by searchAllSites + _build_results_table; read by switch,
# _get_entry, printResultsQuietly, prettyPrintCombinedTopResults.
results: list | None = None
results_tpb_condensed: list | None = None
results_yts: list | None = None
results_eztv: list | None = None
results_1337x: list | None = None
results_rarbg: list = []
num_results: int = 0

# REPL loop state.
query: str = ""
should_exit: bool = False

# Per-source last-used URLs; read by the `u` REPL command.
tpb_url: str = ""
yts_url: str = ""
eztv_url: str = ""
url_1337x: str = ""
tpb_working_domain: str = "thepiratebay.zone"
