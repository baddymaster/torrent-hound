"""Shared mutable state. One module owns it; readers/writers touch it as
`from torrent_hound import state; state.results = ...` to avoid `global`
declarations across the codebase.

During the package-split migration this module sits empty — the monolith
still holds the actual globals. State moves here in Commit 6 (per
tasks/specs/2026-04-17-package-split-design.md).
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
