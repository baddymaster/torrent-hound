"""Per-session result cache.

Populated by `searchAllSites` on successful fetches, checked on subsequent
calls. Keyed by (normalized_query, source_name). TTL-enforced at read time
via `time.monotonic()` — immune to wall-clock changes.
"""
from __future__ import annotations

import time

# Per-session result cache. Populated by searchAllSites on successful fetches,
# checked on subsequent calls. Key: (normalized_query, source_name).
# Value: (fetched_at_monotonic, results_list). TTL is enforced at read time.
_RESULT_CACHE: dict[tuple[str, str], tuple[float, list[dict]]] = {}
_CACHE_TTL_SECONDS = 300  # 5 minutes


def _normalize_query(q: str) -> str:
    """Collapse whitespace differences and case so 'Ubuntu ' and 'ubuntu'
    hit the same cache entry."""
    return q.strip().lower()


def _cache_get(query: str, source: str) -> list[dict] | None:
    """Return cached results if fresh; None if absent or expired.
    Uses time.monotonic() to be immune to wall-clock changes (NTP slew,
    DST, suspend/resume)."""
    key = (_normalize_query(query), source)
    entry = _RESULT_CACHE.get(key)
    if entry is None:
        return None
    fetched_at, results = entry
    if time.monotonic() - fetched_at >= _CACHE_TTL_SECONDS:
        return None
    return results


def _cache_put(query: str, source: str, results: list[dict]) -> None:
    """Store results in the cache. No-op if results is empty — we don't
    want to freeze a transient source error (which surfaces as []) into
    a 5-minute cached-empty state."""
    if not results:
        return
    _RESULT_CACHE[(_normalize_query(query), source)] = (time.monotonic(), results)


def _format_age(seconds: float) -> str:
    """Human-readable age. <60s → '45s', ≥60s → '2m'. TTL caps max
    displayable age at 4m, so no hours/days case is needed."""
    if seconds < 60:
        return f"{int(seconds)}s"
    return f"{int(seconds // 60)}m"


def _print_cache_feedback(cache_hits: dict, miss_names: list, quiet_mode: bool) -> None:
    """Print the user-visible feedback line describing cache hits/misses.
    Suppressed in --quiet / --json modes. Handles the all-hit and mixed
    branches; the all-miss branch is handled by the fetch phase's original
    'Searching ...' message (this function is a no-op when there are no hits)."""
    if quiet_mode or not cache_hits:
        return
    # Lazy import: cache.py loads before ui.py during package initialisation
    # (alphabetical submodule import order in __init__.py). Deferring the
    # `colored` lookup to call time sidesteps the circular-import problem.
    from torrent_hound.ui import colored
    max_age = _format_age(max(cache_hits.values()))
    if not miss_names:
        print(colored.magenta(f"Using cached results ({max_age} old)."))
    else:
        hit_list = ", ".join(cache_hits.keys())
        miss_list = ", ".join(miss_names)
        print(colored.magenta(f"Searching {miss_list}... ({hit_list} cached, {max_age} old)\n"), end='')
