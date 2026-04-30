"""Tests for YTS movie_details.json lazy-fetch helper."""
from unittest.mock import MagicMock, patch

import requests


def test_parse_yts_movie_details_extracts_cast(th, yts_movie_details_json):
    md = th._parse_yts_movie_details(yts_movie_details_json)
    assert md.get("cast")
    # Cap at 5 names → ≤ 4 commas
    assert md["cast"].count(",") <= 4


def test_parse_yts_movie_details_uses_description_full_when_longer(th):
    """When `description_full` is longer than `summary`, prefer it."""
    data = {"data": {"movie": {
        "cast": [{"name": "A"}],
        "description_full": "A much longer plot description that adds context.",
        "summary": "Short.",
    }}}
    md = th._parse_yts_movie_details(data)
    assert md.get("summary", "").startswith("A much longer plot")


def test_parse_yts_movie_details_empty_on_missing_data(th):
    assert th._parse_yts_movie_details({}) == {}
    assert th._parse_yts_movie_details({"data": {}}) == {}
    assert th._parse_yts_movie_details({"data": {"movie": None}}) == {}


def test_fetch_yts_movie_details_returns_empty_on_network_error(th):
    with patch.object(th.requests, "get", side_effect=requests.ConnectionError("nope")):
        assert th._fetch_yts_movie_details(123) == {}


def test_fetch_yts_movie_details_calls_correct_url(th, yts_movie_details_json):
    mock_resp = MagicMock()
    mock_resp.json.return_value = yts_movie_details_json
    mock_resp.status_code = 200
    with patch.object(th.requests, "get", return_value=mock_resp) as mget:
        md = th._fetch_yts_movie_details(42)
    args = mget.call_args
    assert "movie_details.json" in args[0][0]
    assert "movie_id=42" in args[0][0]
    assert "with_cast=true" in args[0][0]
    assert md.get("cast")
