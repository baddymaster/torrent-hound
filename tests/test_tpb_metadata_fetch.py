"""Tests for TPB detail-page parsing (lazy-fetch helper)."""
from unittest.mock import MagicMock, patch

import requests


def test_parse_tpb_detail_extracts_structured_dl_fields(th, tpb_detail_movie_html):
    md = th._parse_tpb_detail_html(tpb_detail_movie_html)
    assert md.get("category", "").startswith("Video")
    assert isinstance(md.get("files"), int) and md["files"] >= 1
    assert md.get("uploaded")              # DD-MM-YYYY
    assert md.get("uploader")              # 'By:' value


def test_parse_tpb_detail_extracts_imdb_code_from_description(th, tpb_detail_movie_html):
    md = th._parse_tpb_detail_html(tpb_detail_movie_html)
    assert md.get("imdb_code", "").startswith("tt")


def test_parse_tpb_detail_extracts_genre_director_cast_plot(th, tpb_detail_movie_html):
    md = th._parse_tpb_detail_html(tpb_detail_movie_html)
    assert md.get("genre")                 # 'Drama, History' from sanitised fixture
    assert md.get("director")
    assert md.get("cast")
    assert md.get("summary")               # from `Plot:` line


def test_parse_tpb_detail_extracts_runtime_from_mediainfo(th, tpb_detail_movie_html):
    md = th._parse_tpb_detail_html(tpb_detail_movie_html)
    runtime = md.get("runtime")
    assert runtime and runtime.endswith("s")  # 'Xh Ym Zs'


def test_parse_tpb_detail_misc_captures_unrecognised_labels(th, tpb_detail_movie_html):
    """Description lines like `INFO:`, `NOTE:`, etc. that don't match a
    known field land in `misc` so users still see them."""
    md = th._parse_tpb_detail_html(tpb_detail_movie_html)
    if "misc" in md:
        assert isinstance(md["misc"], dict)
        for k, v in md["misc"].items():
            assert isinstance(k, str) and isinstance(v, str)


def test_parse_tpb_detail_iso_returns_sparse_metadata(th, tpb_detail_iso_html):
    """ISO pages don't typically have IMDB / genre / director / cast /
    runtime — just the structured fields and maybe a description."""
    md = th._parse_tpb_detail_html(tpb_detail_iso_html)
    assert md.get("category")
    assert md.get("files") is not None
    assert md.get("uploaded")
    if "imdb_code" in md:
        assert md["imdb_code"].startswith("tt")


def test_parse_tpb_detail_garbage_returns_empty_dict(th):
    assert th._parse_tpb_detail_html(b"<html></html>") == {}
    assert th._parse_tpb_detail_html(b"") == {}


def test_fetch_tpb_metadata_returns_empty_on_network_error(th):
    with patch.object(th.requests, "get", side_effect=requests.ConnectionError("nope")):
        assert th._fetch_tpb_metadata("https://example.test/torrent/123/") == {}


def test_fetch_tpb_metadata_passes_html_to_parser(th, tpb_detail_movie_html):
    mock_resp = MagicMock()
    mock_resp.content = tpb_detail_movie_html
    mock_resp.status_code = 200
    with patch.object(th.requests, "get", return_value=mock_resp):
        md = th._fetch_tpb_metadata("https://example.test/torrent/123/")
    assert md.get("uploader")
    assert md.get("imdb_code", "").startswith("tt")
