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


# ── format-variant tests (R1/R2/R3/R8 captured from real searches) ────

def test_parse_tpb_detail_R1_extracts_multiline_director_block(th, tpb_detail_r1_html):
    """`Directors\\nName One\\nName Two\\n\\n` block format (no colon, names
    on their own lines). Parser must capture all directors, comma-joined."""
    md = th._parse_tpb_detail_html(tpb_detail_r1_html)
    assert md.get("director")
    assert "Director One" in md["director"]
    assert "Director Two" in md["director"]


def test_parse_tpb_detail_R1_extracts_multiline_stars_block(th, tpb_detail_r1_html):
    md = th._parse_tpb_detail_html(tpb_detail_r1_html)
    assert md.get("cast")
    # Top 5 cap; fixture has 3
    assert "Actor A" in md["cast"]
    assert "Actor B" in md["cast"]


def test_parse_tpb_detail_R1_extracts_bare_paragraph_plot(th, tpb_detail_r1_html):
    """No `Plot:` label — first long paragraph in the description is the plot."""
    md = th._parse_tpb_detail_html(tpb_detail_r1_html)
    assert md.get("summary", "").startswith("A short placeholder plot")


def test_parse_tpb_detail_R2_extracts_slash_genre_line(th, tpb_detail_r2_html):
    """Genre as a bare slash-separated line (no `Genre:` label)."""
    md = th._parse_tpb_detail_html(tpb_detail_r2_html)
    assert md.get("genre")
    assert "/" in md["genre"]
    assert "Action" in md["genre"]


def test_parse_tpb_detail_R2_extracts_imdb_and_bare_plot(th, tpb_detail_r2_html):
    md = th._parse_tpb_detail_html(tpb_detail_r2_html)
    assert md.get("imdb_code", "").startswith("tt")
    assert md.get("summary", "").startswith("A short placeholder plot")


def test_parse_tpb_detail_R3_extracts_bracketed_runtime(th, tpb_detail_r3_html):
    """`[RUNTIME]:.[ 1Hr 32Min` — extract runtime in 'Xh Ym Zs' format."""
    md = th._parse_tpb_detail_html(tpb_detail_r3_html)
    assert md.get("runtime")
    assert "1h" in md["runtime"]
    assert "32m" in md["runtime"]


def test_parse_tpb_detail_R3_misc_captures_bracketed_labels(th, tpb_detail_r3_html):
    """Bracketed `[FRAME RATE]`, `[AUDIO STREAM 1]`, `[SUBTITLES]` etc.
    must surface in `misc` so the user sees them."""
    md = th._parse_tpb_detail_html(tpb_detail_r3_html)
    misc = md.get("misc") or {}
    keys_upper = {k.upper() for k in misc}
    assert "FRAME RATE" in keys_upper
    assert "SUBTITLES" in keys_upper
    # At least one audio stream surfaces
    assert any("AUDIO" in k for k in keys_upper)


def test_parse_tpb_detail_R8_extracts_aligned_duration(th, tpb_detail_r8_html):
    """`Duration        : 1 h 32 min` — extract runtime."""
    md = th._parse_tpb_detail_html(tpb_detail_r8_html)
    assert md.get("runtime")
    assert "1h" in md["runtime"]


def test_parse_tpb_detail_R8_misc_captures_video_audio_subtitle_rows(th, tpb_detail_r8_html):
    """Aligned `Codec : AVC`, `Frame Rate : 23.976`, `Subtitle(s) : ...`
    rows should appear in `misc` so the user sees the encode details."""
    md = th._parse_tpb_detail_html(tpb_detail_r8_html)
    misc = md.get("misc") or {}
    # At least one video / audio / subtitle field surfaced
    assert any(k.lower().startswith(("codec", "frame", "bitrate", "subtitle"))
               for k in misc)


def test_fetch_tpb_metadata_passes_html_to_parser(th, tpb_detail_movie_html):
    mock_resp = MagicMock()
    mock_resp.content = tpb_detail_movie_html
    mock_resp.status_code = 200
    with patch.object(th.requests, "get", return_value=mock_resp):
        md = th._fetch_tpb_metadata("https://example.test/torrent/123/")
    assert md.get("uploader")
    assert md.get("imdb_code", "").startswith("tt")
