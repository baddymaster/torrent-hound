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

import time
from concurrent.futures import ThreadPoolExecutor

from torrent_hound import state
from torrent_hound.cache import (
    _RESULT_CACHE,
    _cache_get,
    _cache_put,
    _format_age,
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

    `progress_callback`, if provided, is `callable(source_name, event)` where
    `event` is a dict carrying one of these `type`s:

      {"type": "start"}
          fetch of this source has begun (no mirror tried yet)
      {"type": "mirror_attempt", "mirror": "..."}
          source is now trying this mirror
      {"type": "mirror_failed", "mirror": "..."}
          mirror failed; source will move to the next
      {"type": "ok", "count": N, "elapsed_ms": T, "mirror": "..."}
          source returned N results from this mirror in T ms
      {"type": "empty", "elapsed_ms": T}
          mirrors responded but no results
      {"type": "failed", "elapsed_ms": T}
          all mirrors exhausted / unreachable
      {"type": "cached", "count": N, "age": "3m"}
          served from cache (no network); only emitted by searchAllSites itself

    Sources emit start / mirror_* / ok / empty / failed; searchAllSites
    emits `cached` for cache hits.
    """
    if query is None:
        query = _DEFAULT_QUERY

    def _emit(name, event):
        if progress_callback is not None:
            progress_callback(name, event)

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
                age_seconds = time.monotonic() - fetched_at
                cache_hits[name] = age_seconds
                source_results[name] = cached
                _emit(name, {"type": "cached", "count": len(cached), "age": _format_age(age_seconds)})
            else:
                misses.append((name, fn))
    else:
        misses = list(_SOURCES)

    _print_cache_feedback(cache_hits, [name for name, _ in misses], quiet_mode)

    # Fetch phase: only sources that missed. Each source gets a per-source
    # progress closure that prefills elapsed_ms when the source forgot to.
    if misses:
        if not quiet_mode and not cache_hits:
            miss_names = ", ".join(name for name, _ in misses)
            print(colored.magenta(f"Searching {miss_names}...\n"), end='')

        def _per_source_progress(name, started_at):
            def emit(event):
                # Sources can omit elapsed_ms on terminal events; fill it in here
                # so they don't all need to thread time.monotonic() through.
                if event.get("type") in ("ok", "empty", "failed") and "elapsed_ms" not in event:
                    event["elapsed_ms"] = int((time.monotonic() - started_at) * 1000)
                _emit(name, event)
            return emit

        with ThreadPoolExecutor(max_workers=max(1, len(misses))) as pool:
            started = {name: time.monotonic() for name, _ in misses}
            for name, _ in misses:
                _emit(name, {"type": "start"})
            futures = {
                name: pool.submit(fn, query, quiet_mode, progress=_per_source_progress(name, started[name]))
                for name, fn in misses
            }
            for name, fut in futures.items():
                result = fut.result() or []
                source_results[name] = result
                _cache_put(query, name, result)

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
