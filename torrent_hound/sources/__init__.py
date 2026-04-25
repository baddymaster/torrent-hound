"""Torrent source registry + the `searchAllSites` orchestrator.

Each entry in `_SOURCES` is `(display_name, callable)` where the callable
matches the `Source` Protocol from `sources.base`: takes `(query,
quiet_mode)` and returns a list of result dicts. Adding a new source is:

  1. create `sources/new_source.py` implementing a `search*` function
  2. import + register it in the `_SOURCES` list below

`searchAllSites` handles cache lookup, parallel fan-out for cache-missed
sources, and writes results back to module-level state that the REPL and
UI layers read. State still lives on the `torrent_hound` package itself
during the migration — moves to `torrent_hound.state` in a later commit.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

from torrent_hound import state
from torrent_hound.cache import (
    _RESULT_CACHE,
    _cache_get,
    _cache_put,
    _normalize_query,
    _print_cache_feedback,
)
from torrent_hound.ui import colored

from .eztv import searchEZTV
from .tpb import searchPirateBayCondensed
from .yts import searchYTS

# Registry of active torrent sources. Each entry is (display_name, callable)
# where the callable matches the Source protocol from .base.
# To re-enable 1337x: uncomment its entry (and see legacy_1337x.search1337x
# for Cloudflare caveats).
_SOURCES = [
    ('TPB', searchPirateBayCondensed),
    ('YTS', searchYTS),
    ('EZTV', searchEZTV),
    # ('1337x', search1337x),
]


_DEFAULT_QUERY = 'ubuntu'


def searchAllSites(query=None, force_search=False, quiet_mode=False, progress_callback=None):
    """Fan out across registered sources, with cache + fallback.

    `progress_callback`, if provided, receives `(source_name, status)` where
    status is one of: "fetching", "cached", "ok:N", "empty". Used by the TUI
    to render the per-source progress strip during loading.
    """
    if query is None:
        query = _DEFAULT_QUERY

    def _emit(name, status):
        if progress_callback is not None:
            progress_callback(name, status)

    if force_search:
        state.results_1337x = None
        state.results_yts = None
        state.results_eztv = None
        state.results = None
        state.results_tpb_condensed = None

    # RARBG and SkyTorrents permanently removed. See git history.
    state.results_rarbg = []

    # Cache read phase: resolve each source from cache if fresh; else queue for fetch.
    source_results: dict = {}
    misses: list = []
    cache_hits: dict = {}  # source_name → age_in_seconds (for feedback)

    if not force_search:
        for name, fn in _SOURCES:
            cached = _cache_get(query, name)
            if cached is not None:
                fetched_at = _RESULT_CACHE[(_normalize_query(query), name)][0]
                cache_hits[name] = time.monotonic() - fetched_at
                source_results[name] = cached
                _emit(name, "cached")
            else:
                misses.append((name, fn))
                _emit(name, "fetching")
    else:
        misses = list(_SOURCES)
        for name, _ in misses:
            _emit(name, "fetching")

    _print_cache_feedback(cache_hits, [name for name, _ in misses], quiet_mode)

    # Fetch phase: only sources that missed.
    if misses:
        if not quiet_mode and not cache_hits:
            # All-miss case — emit the original "Searching ..." message.
            miss_names = ", ".join(name for name, _ in misses)
            print(colored.magenta(f"Searching {miss_names}...\n"), end='')

        with ThreadPoolExecutor(max_workers=max(1, len(misses))) as pool:
            futures = {name: pool.submit(fn, query, quiet_mode) for name, fn in misses}
            for name, fut in futures.items():
                result = fut.result() or []
                source_results[name] = result
                _cache_put(query, name, result)
                _emit(name, f"ok:{len(result)}" if result else "empty")

        if not quiet_mode:
            print(colored.green("Done."))

    def _tag(rows, source):
        # Tag each row with its source so the TUI can show per-row attribution.
        # Idempotent via setdefault — cached re-runs don't re-tag.
        for r in rows:
            r.setdefault('source', source)
        return rows

    state.results_tpb_condensed = _tag(source_results.get('TPB', []), 'TPB')
    state.results_yts = _tag(source_results.get('YTS', []), 'YTS')
    state.results_eztv = _tag(source_results.get('EZTV', []), 'EZTV')
    state.results_1337x = _tag(source_results.get('1337x', []), '1337x')
    # Flat list for the TUI — result indices span all sources sequentially
    state.results = (
        state.results_tpb_condensed
        + state.results_yts
        + state.results_eztv
        + state.results_1337x
    )
