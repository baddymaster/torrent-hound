"""Integration tests for the in-memory result cache.

These exercise searchAllSites end-to-end: monkeypatch _SOURCES with
MagicMock callables and (where needed) time.monotonic to control TTL.
The autouse clean_cache fixture resets cache + globals between tests
so each test starts from a clean slate.

No tests for the feedback strings — cosmetic, would be brittle.
"""
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def clean_cache(th):
    """Reset the cache and result globals before and after each test."""
    th._RESULT_CACHE.clear()
    th.state.results = []
    th.state.results_tpb_condensed = []
    th.state.results_yts = []
    th.state.results_eztv = []
    th.state.results_1337x = []
    yield
    th._RESULT_CACHE.clear()


@pytest.fixture
def mock_sources(th, monkeypatch):
    """Replace _SOURCES with three MagicMocks returning distinct results.
    Returns a dict {source_name: mock} for assertion convenience."""
    tpb_mock = MagicMock(return_value=[{"name": "tpb-result", "size": "1G"}])
    yts_mock = MagicMock(return_value=[{"name": "yts-result", "size": "500M"}])
    eztv_mock = MagicMock(return_value=[{"name": "eztv-result", "size": "200M"}])
    monkeypatch.setattr(th.sources, "_SOURCES", [
        ("TPB", tpb_mock),
        ("YTS", yts_mock),
        ("EZTV", eztv_mock),
    ])
    return {"TPB": tpb_mock, "YTS": yts_mock, "EZTV": eztv_mock}


def test_cache_miss_calls_source(th, mock_sources):
    """First call fans out to every source exactly once."""
    th.searchAllSites("ubuntu", quiet_mode=True)
    assert mock_sources["TPB"].call_count == 1
    assert mock_sources["YTS"].call_count == 1
    assert mock_sources["EZTV"].call_count == 1


def test_cache_hit_skips_source(th, mock_sources):
    """Second call within TTL does not invoke any source mock."""
    th.searchAllSites("ubuntu", quiet_mode=True)
    for m in mock_sources.values():
        m.reset_mock()
    th.searchAllSites("ubuntu", quiet_mode=True)
    for m in mock_sources.values():
        assert m.call_count == 0


def test_ttl_expiry_triggers_refetch(th, mock_sources, monkeypatch):
    """Advancing monotonic past TTL causes sources to be called again."""
    monkeypatch.setattr(th.time, "monotonic", lambda: 1000.0)
    th.searchAllSites("ubuntu", quiet_mode=True)
    for m in mock_sources.values():
        m.reset_mock()
    # 301 seconds later — past the 300s TTL.
    monkeypatch.setattr(th.time, "monotonic", lambda: 1301.0)
    th.searchAllSites("ubuntu", quiet_mode=True)
    for m in mock_sources.values():
        assert m.call_count == 1


def test_force_search_bypasses_cache_read(th, mock_sources):
    """force_search=True invokes sources even when cache is warm."""
    th.searchAllSites("ubuntu", quiet_mode=True)
    for m in mock_sources.values():
        m.reset_mock()
    th.searchAllSites("ubuntu", force_search=True, quiet_mode=True)
    for m in mock_sources.values():
        assert m.call_count == 1


def test_force_search_updates_cache(th, mock_sources):
    """After a force-fetch, a subsequent non-forced call sees fresh data."""
    th.searchAllSites("ubuntu", quiet_mode=True)  # populate with original data
    # Swap mocks to return NEW data
    mock_sources["TPB"].return_value = [{"name": "tpb-NEW", "size": "2G"}]
    th.searchAllSites("ubuntu", force_search=True, quiet_mode=True)  # force refresh
    for m in mock_sources.values():
        m.reset_mock()
    # Non-forced call: should return the NEW data without invoking sources.
    th.searchAllSites("ubuntu", quiet_mode=True)
    for m in mock_sources.values():
        assert m.call_count == 0
    assert th.state.results_tpb_condensed[0]["name"] == "tpb-NEW"


def test_query_normalization_hits_same_entry(th, mock_sources):
    """'Ubuntu ' (cap, trailing space) and 'ubuntu' share a cache entry."""
    th.searchAllSites("Ubuntu  ", quiet_mode=True)
    for m in mock_sources.values():
        m.reset_mock()
    th.searchAllSites("ubuntu", quiet_mode=True)
    for m in mock_sources.values():
        assert m.call_count == 0


def test_empty_results_not_cached(th, monkeypatch):
    """Sources returning [] are not cached; next call re-invokes them."""
    tpb_mock = MagicMock(return_value=[])
    yts_mock = MagicMock(return_value=[])
    eztv_mock = MagicMock(return_value=[])
    monkeypatch.setattr(th.sources, "_SOURCES", [
        ("TPB", tpb_mock),
        ("YTS", yts_mock),
        ("EZTV", eztv_mock),
    ])
    th.searchAllSites("obscure-query", quiet_mode=True)
    assert len(th._RESULT_CACHE) == 0  # nothing cached
    th.searchAllSites("obscure-query", quiet_mode=True)
    for m in (tpb_mock, yts_mock, eztv_mock):
        assert m.call_count == 2  # re-invoked


def test_mixed_hit_miss_only_fetches_missed_source(th, mock_sources):
    """Pre-populating cache for one source means only the others are fetched."""
    th._cache_put("ubuntu", "TPB", [{"name": "cached-tpb"}])
    th.searchAllSites("ubuntu", quiet_mode=True)
    assert mock_sources["TPB"].call_count == 0
    assert mock_sources["YTS"].call_count == 1
    assert mock_sources["EZTV"].call_count == 1
    assert th.state.results_tpb_condensed[0]["name"] == "cached-tpb"


def test_source_exception_does_not_tank_orchestrator(th, monkeypatch):
    """If one source raises an unhandled exception, the orchestrator must
    survive: surviving sources' results reach the user, state.results gets
    populated, and the broken source emits a synthetic `failed` terminal
    event so the TUI's source-trail spinner settles instead of staying
    visually mid-flight forever."""
    tpb_mock = MagicMock(side_effect=AttributeError("simulated parser crash"))
    yts_mock = MagicMock(return_value=[{"name": "yts-result", "size": "500M"}])
    eztv_mock = MagicMock(return_value=[{"name": "eztv-result", "size": "200M"}])
    monkeypatch.setattr(th.sources, "_SOURCES", [
        ("TPB", tpb_mock),
        ("YTS", yts_mock),
        ("EZTV", eztv_mock),
    ])

    events: list = []
    def capture(name, event):
        events.append((name, event["type"]))

    th.searchAllSites("anything", quiet_mode=True, progress_callback=capture)

    assert th.state.results_yts and th.state.results_yts[0]["name"] == "yts-result"
    assert th.state.results_eztv and th.state.results_eztv[0]["name"] == "eztv-result"
    assert th.state.results_tpb_condensed == []
    assert th.state.results  # flat list populated, not None
    tpb_event_types = [t for n, t in events if n == "TPB"]
    assert "failed" in tpb_event_types
