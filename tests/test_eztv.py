"""Tests for the EZTV source: query parsing, IMDB bridge, JSON parser,
episode/keyword filtering, domain fallback, and error handling."""
from unittest.mock import MagicMock, patch

import requests

# ---------------------------------------------------------------------------
# _parse_episode_query
# ---------------------------------------------------------------------------

def test_parse_episode_query_with_season_and_episode(th):
    q, s, e, f = th._parse_episode_query("game of thrones s05e05")
    assert q == "game of thrones"
    assert s == "5"
    assert e == "5"
    assert f == []


def test_parse_episode_query_season_only(th):
    q, s, e, f = th._parse_episode_query("breaking bad s02")
    assert q == "breaking bad"
    assert s == "2"
    assert e is None
    assert f == []


def test_parse_episode_query_no_episode_info(th):
    q, s, e, f = th._parse_episode_query("severance")
    assert q == "severance"
    assert s is None
    assert e is None
    assert f == []


def test_parse_episode_query_case_insensitive(th):
    q1, s1, e1, _ = th._parse_episode_query("show S5E3")
    q2, s2, e2, _ = th._parse_episode_query("show s5e3")
    assert (q1, s1, e1) == (q2, s2, e2)
    assert s1 == "5"
    assert e1 == "3"


def test_parse_episode_query_strips_leading_zeros(th):
    _, s, e, _ = th._parse_episode_query("show s01e02")
    assert s == "1"
    assert e == "2"


def test_parse_episode_query_with_quality_filters(th):
    q, s, e, f = th._parse_episode_query("sherlock s01e01 1080p x265")
    assert q == "sherlock"
    assert s == "1"
    assert e == "1"
    assert "1080p" in f
    assert "x265" in f


def test_parse_episode_query_filters_without_episode(th):
    q, s, e, f = th._parse_episode_query("the bear 720p")
    assert q == "the bear"
    assert s is None
    assert e is None
    assert f == ["720p"]


def test_parse_episode_query_web_dl_filter(th):
    q, s, e, f = th._parse_episode_query("show s01e01 web-dl")
    assert "web-dl" in f


# ---------------------------------------------------------------------------
# _parse_eztv_json
# ---------------------------------------------------------------------------

def test_parse_eztv_json_returns_results(th, eztv_severance_json):
    torrents = eztv_severance_json.get("torrents", [])
    results = th._parse_eztv_json(torrents)
    assert len(results) > 0


def test_parse_eztv_json_respects_limit(th, eztv_severance_json):
    torrents = eztv_severance_json.get("torrents", [])
    results = th._parse_eztv_json(torrents, limit=3)
    assert len(results) == 3


def test_parse_eztv_json_filters_by_season_and_episode(th, eztv_severance_json):
    torrents = eztv_severance_json.get("torrents", [])
    results = th._parse_eztv_json(torrents, season="2", episode="5", limit=50)
    for r in results:
        assert "S02E05" in r["name"] or "s02e05" in r["name"].lower()


def test_parse_eztv_json_filters_by_season_only(th, eztv_severance_json):
    torrents = eztv_severance_json.get("torrents", [])
    results = th._parse_eztv_json(torrents, season="2", limit=50)
    assert len(results) > 0
    # All results should be season 2 — check the raw torrent data
    s2_ids = {t["id"] for t in torrents if t.get("season") == "2"}
    for r in results:
        # link contains the torrent ID
        assert any(str(tid) in r["link"] for tid in s2_ids)


def test_parse_eztv_json_filters_by_keyword(th, eztv_severance_json):
    torrents = eztv_severance_json.get("torrents", [])
    results = th._parse_eztv_json(torrents, filters=["1080p"], limit=50)
    for r in results:
        assert "1080p" in r["name"].lower()


def test_parse_eztv_json_combined_episode_and_keyword_filter(th, eztv_severance_json):
    torrents = eztv_severance_json.get("torrents", [])
    results = th._parse_eztv_json(torrents, season="2", episode="5", filters=["1080p"], limit=50)
    for r in results:
        assert "1080p" in r["name"].lower()
        assert "S02E05" in r["name"] or "s02e05" in r["name"].lower()


def test_parse_eztv_json_no_filter_returns_all(th, eztv_severance_json):
    torrents = eztv_severance_json.get("torrents", [])
    results = th._parse_eztv_json(torrents, limit=200)
    # Without filters, should return up to limit entries
    assert len(results) == len(torrents) or len(results) == 200


def test_parse_eztv_json_each_result_has_required_fields(th, eztv_severance_json):
    required = {"name", "link", "seeders", "leechers", "magnet", "size", "ratio"}
    torrents = eztv_severance_json.get("torrents", [])
    for r in th._parse_eztv_json(torrents, limit=10):
        assert required.issubset(r.keys()), f"missing fields in {r}"


def test_parse_eztv_json_magnet_starts_with_magnet_scheme(th, eztv_severance_json):
    torrents = eztv_severance_json.get("torrents", [])
    for r in th._parse_eztv_json(torrents, limit=10):
        assert r["magnet"].startswith("magnet:?"), r["magnet"]


def test_parse_eztv_json_link_uses_provided_domain(th, eztv_severance_json):
    torrents = eztv_severance_json.get("torrents", [])
    results = th._parse_eztv_json(torrents, domain="eztv.re", limit=3)
    for r in results:
        assert "eztv.re" in r["link"]


def test_parse_eztv_json_empty_on_no_torrents(th):
    assert th._parse_eztv_json([]) == []
    assert th._parse_eztv_json(None or []) == []


# ---------------------------------------------------------------------------
# _format_bytes
# ---------------------------------------------------------------------------

def test_format_bytes(th):
    assert th._format_bytes(0) == "0.0 B"
    assert th._format_bytes(1023) == "1023.0 B"
    assert th._format_bytes(1024) == "1.0 KB"
    assert th._format_bytes(1536) == "1.5 KB"
    assert "MB" in th._format_bytes(5 * 1024 * 1024)
    assert "GB" in th._format_bytes(2 * 1024**3)


# ---------------------------------------------------------------------------
# _imdb_lookup (mocked — no network)
# ---------------------------------------------------------------------------

def test_imdb_lookup_finds_tv_series(th, imdb_suggestion_severance_json):
    """Mock the IMDB request and verify we extract the right tvSeries ID."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = imdb_suggestion_severance_json

    with patch.object(th.requests, "get", return_value=mock_resp):
        result = th._imdb_lookup("severance")
        assert result == "11280740"


def test_imdb_lookup_returns_none_for_nonsense(th):
    """If IMDB returns no tvSeries match, should return None."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"d": [{"id": "tt999", "qid": "movie", "l": "Some Movie"}]}

    with patch.object(th.requests, "get", return_value=mock_resp):
        assert th._imdb_lookup("xyzzy_not_a_show_12345") is None


def test_imdb_lookup_returns_none_on_network_error(th):
    with patch.object(th.requests, "get", side_effect=requests.ConnectionError("nope")):
        assert th._imdb_lookup("anything") is None


# ---------------------------------------------------------------------------
# searchEZTV integration (mocked)
# ---------------------------------------------------------------------------

def test_searchEZTV_fallback_on_dead_domain(th, eztv_severance_json):
    """First domain fails, second returns results."""
    def fake_get(url, **kwargs):
        if "dead.invalid" in url:
            raise requests.ConnectionError("nope")
        # IMDB lookup
        if "imdb.com" in url:
            resp = MagicMock()
            resp.json.return_value = {"d": [{"id": "tt11280740", "qid": "tvSeries", "l": "Severance"}]}
            return resp
        # EZTV API
        resp = MagicMock()
        resp.json.return_value = eztv_severance_json
        return resp

    with patch.object(th, "EZTV_DOMAINS", ["dead.invalid", "eztvx.to"]):
        with patch.object(th.requests, "get", side_effect=fake_get):
            results = th.searchEZTV("severance", timeout=1)
            assert len(results) > 0


def test_searchEZTV_shows_error_when_imdb_fails(th, capsys):
    """When IMDB returns no TV match, user sees a clear message."""
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"d": []}

    with patch.object(th.requests, "get", return_value=mock_resp):
        results = th.searchEZTV("xyzzy_not_a_show")
        assert results == []
        assert "No matching TV show" in capsys.readouterr().out


def test_searchEZTV_shows_error_when_all_domains_fail(th, capsys):
    """When all EZTV domains are unreachable, user sees a clear message."""
    call_count = [0]

    def fake_get(url, **kwargs):
        call_count[0] += 1
        # First call is IMDB — let it succeed
        if "imdb.com" in url:
            resp = MagicMock()
            resp.json.return_value = {"d": [{"id": "tt11280740", "qid": "tvSeries", "l": "Severance"}]}
            return resp
        # All EZTV calls fail
        raise requests.ConnectionError("all dead")

    with patch.object(th.requests, "get", side_effect=fake_get):
        results = th.searchEZTV("severance")
        assert results == []
        assert "unreachable" in capsys.readouterr().out
