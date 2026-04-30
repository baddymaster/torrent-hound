# PYTHON_ARGCOMPLETE_OK
"""torrent_hound — multi-source torrent search CLI.

Re-export surface for tests and downstream callers (`import torrent_hound;
torrent_hound.foo()`). Prefer importing from submodules in new code.

Module layout (post Phase C package split):

    cli.py        — argparse + main() entry point
    repl.py       — interactive REPL (switch, print_menu, _cmd_* handlers)
    ui.py         — rich Console, colored shim, table builders, JSON printers
    state.py      — shared mutable state (results, urls, exit flag)
    cache.py      — per-session result cache
    config.py     — TOML config + Real-Debrid setup commands
    realdebrid.py — RD API client + the rd<n> command handler
    sources/      — one module per torrent source + the orchestrator
"""
# Stdlib + third-party re-exports — kept on the package namespace for tests
# that use `mock.patch.object(th.X, ...)` to monkey-patch behaviour during
# unit tests. New code should import these directly from their original
# modules; these re-exports exist only to keep the existing test suite
# passing without rewriting every patch path.
import getpass  # noqa: F401
import os  # noqa: F401
import socket  # noqa: F401
import sys
import time  # noqa: F401
import urllib.parse  # noqa: F401
import webbrowser  # noqa: F401

import argcomplete  # noqa: F401
import platformdirs  # noqa: F401
import pyperclip  # noqa: F401
import requests  # noqa: F401
import tomli_w  # noqa: F401
from bs4 import BeautifulSoup  # noqa: F401

if sys.version_info >= (3, 11):
    import tomllib  # noqa: F401
else:
    import tomli as tomllib  # noqa: F401  — backport; same API surface we use

# Submodules — exposed so tests can do `th.state.results = ...`,
# `monkeypatch.setattr(th.config, "_load_config", ...)`, etc.
from . import (
    cache,  # noqa: F401
    config,  # noqa: F401
    realdebrid,  # noqa: F401
    sources,  # noqa: F401
    state,  # noqa: F401
    tui,  # noqa: F401
    ui,  # noqa: F401
)
from . import cli as _cli  # noqa: F401  — `cli` collides with no public name; alias avoids confusion

# Functional re-exports — names that tests + downstream callers reference as
# `torrent_hound.X`. Each subsystem's public surface flattened to the package.
from .cache import (  # noqa: F401
    _CACHE_TTL_SECONDS,
    _RESULT_CACHE,
    _cache_get,
    _cache_put,
    _format_age,
    _normalize_query,
    _print_cache_feedback,
)
from .cli import _build_parser, defaultQuery, main  # noqa: F401
from .config import (  # noqa: F401
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
from .realdebrid import (  # noqa: F401
    _ANSI_ESCAPE_RE,
    _RD_API,
    _RD_ERROR_MESSAGES,
    _RD_HASH_RE,
    _cmd_rd,
    _human_size,
    _rd_add_magnet,
    _rd_apply_action,
    _rd_check_cached,
    _rd_dispatch,
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
from .sources import _SOURCES, searchAllSites  # noqa: F401
from .sources.base import _format_bytes, removeAndReplaceSpaces  # noqa: F401
from .sources.eztv import (  # noqa: F401
    EZTV_DOMAINS,
    _eztv_slug,
    _imdb_lookup,
    _parse_episode_query,
    _parse_eztv_json,
    searchEZTV,
)
from .sources.legacy_1337x import (  # noqa: F401
    extract_magnet_link_1337x,
    pretty_print_top_results_1337x,
    search1337x,
)
from .sources.tpb import (  # noqa: F401
    TPB_DOMAINS,
    _parse_tpb_html,
    _tpb_page_is_empty_results,
    searchPirateBayCondensed,
)
from .sources.yts import (  # noqa: F401
    YTS_DOMAINS,
    YTS_TRACKERS,
    _build_yts_magnet,
    _extract_yts_quality,
    _parse_yts_json,
    searchYTS,
)
from .ui import (  # noqa: F401
    _build_results_table,
    colored,
    console,
    convertListJSONToPureJSON,
    pretty_print_top_results_piratebay,
    prettyPrintCombinedTopResults,
    printResultsQuietly,
    printTopResults,
)

__version__ = _cli.__version__
