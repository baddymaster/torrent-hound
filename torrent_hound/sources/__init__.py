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

from torrent_hound.cache import (
    _RESULT_CACHE,
    _cache_get,
    _cache_put,
    _normalize_query,
    _print_cache_feedback,
)

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


def searchAllSites(query=None, force_search=False, quiet_mode=False):
    # Lazy reference to the package so we can read/write shared globals that
    # still live in _monolith (state.py takes over in Commit 6).
    import torrent_hound as _th

    if query is None:
        query = _th.defaultQuery

    if force_search:
        _th.results_1337x = None
        _th.results_yts = None
        _th.results_eztv = None
        _th.results = None
        _th.results_tpb_condensed = None

    # RARBG and SkyTorrents permanently removed. See git history.
    _th.results_rarbg = []

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
            else:
                misses.append((name, fn))
    else:
        misses = list(_SOURCES)

    _print_cache_feedback(cache_hits, [name for name, _ in misses], quiet_mode)

    # Fetch phase: only sources that missed.
    if misses:
        if not quiet_mode and not cache_hits:
            # All-miss case — emit the original "Searching ..." message.
            miss_names = ", ".join(name for name, _ in misses)
            print(_th.colored.magenta(f"Searching {miss_names}...\n"), end='')

        with ThreadPoolExecutor(max_workers=max(1, len(misses))) as pool:
            futures = {name: pool.submit(fn, query, quiet_mode) for name, fn in misses}
            for name, fut in futures.items():
                result = fut.result() or []
                source_results[name] = result
                _cache_put(query, name, result)

        if not quiet_mode:
            print(_th.colored.green("Done."))

    _th.results_tpb_condensed = source_results.get('TPB', [])
    _th.results_yts = source_results.get('YTS', [])
    _th.results_eztv = source_results.get('EZTV', [])
    _th.results_1337x = source_results.get('1337x', [])
    # Flat list for switch() — result numbers span all sources sequentially
    _th.results = (
        _th.results_tpb_condensed
        + _th.results_yts
        + _th.results_eztv
        + _th.results_1337x
    )
