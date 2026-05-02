"""Tests for shared parser helpers in torrent_hound/sources/base.py."""


def test_fmt_date_unix_int(th):
    # 1700000000 = 2023-11-14 22:13:20 UTC
    assert th._fmt_date(1700000000) == "14-11-2023"


def test_fmt_date_iso_with_time(th):
    assert th._fmt_date("2024-09-12 14:30:00") == "12-09-2024"


def test_fmt_date_iso_with_tz_suffix(th):
    """TPB's `Uploaded:` field carries a 'GMT' suffix."""
    assert th._fmt_date("2024-09-12 14:30:00 GMT") == "12-09-2024"


def test_fmt_date_bare_date(th):
    assert th._fmt_date("2024-09-12") == "12-09-2024"


def test_fmt_date_returns_none_on_garbage(th):
    assert th._fmt_date("not a date") is None
    assert th._fmt_date("") is None
    assert th._fmt_date(None) is None


def test_fmt_date_returns_none_on_zero_unix(th):
    """Treat 1970-01-01 epoch-zero as 'no value', since most APIs use 0
    as a missing-date sentinel."""
    assert th._fmt_date(0) is None


def test_fmt_runtime_full_hms(th):
    # 2h 16m 22s = 2*3600 + 16*60 + 22 = 8182 seconds
    assert th._fmt_runtime(8182) == "2h 16m 22s"


def test_fmt_runtime_drops_leading_zero_hours(th):
    """A 25-minute short renders as '25m', not '0h 25m 0s'."""
    assert th._fmt_runtime(1500) == "25m"


def test_fmt_runtime_drops_leading_zero_h_and_m(th):
    """45-second clip renders as '45s', not '0h 0m 45s'."""
    assert th._fmt_runtime(45) == "45s"


def test_fmt_runtime_drops_trailing_zero_seconds(th):
    """2h 10m exactly renders as '2h 10m', not '2h 10m 0s'."""
    assert th._fmt_runtime(7800) == "2h 10m"


def test_fmt_runtime_keeps_zero_minutes_when_h_and_s_both_set(th):
    """1h 0m 22s — keep the middle 0m for clarity ('1h 22s' is ambiguous)."""
    assert th._fmt_runtime(3622) == "1h 0m 22s"


def test_fmt_runtime_exactly_one_hour(th):
    assert th._fmt_runtime(3600) == "1h"


def test_fmt_runtime_returns_none_on_zero_or_none(th):
    assert th._fmt_runtime(0) is None
    assert th._fmt_runtime(None) is None


def test_extract_release_tags_full_movie_name(th):
    out = th._extract_release_tags("Some.Movie.2024.1080p.BluRay.x265.REPACK")
    assert out == {
        "quality": "1080p",
        "codec": "x265",
        "source_type": "BluRay",
        "repack": True,
    }


def test_extract_release_tags_episode(th):
    out = th._extract_release_tags("Some.Show.S04E12.2160p.WEB-DL.x264")
    assert out["season"] == 4
    assert out["episode"] == 12
    assert out["quality"] == "2160p"
    assert out["codec"] == "x264"
    assert out["source_type"] == "WEB-DL"


def test_extract_release_tags_season_only(th):
    out = th._extract_release_tags("Some.Show.S01.Complete.1080p")
    assert out["season"] == 1
    assert "episode" not in out


def test_extract_release_tags_case_insensitive(th):
    out = th._extract_release_tags("foo 1080P bluray X264")
    assert out["quality"] == "1080p"
    assert out["codec"] == "x264"
    assert out["source_type"].lower() == "bluray"


def test_extract_release_tags_no_match_returns_empty(th):
    assert th._extract_release_tags("ubuntu-24.04.1-desktop-amd64.iso") == {}


def test_extract_release_tags_repack_proper_alias(th):
    """PROPER and REPACK both flip the repack flag."""
    assert th._extract_release_tags("foo PROPER")["repack"] is True
    assert th._extract_release_tags("foo REPACK")["repack"] is True


def test_metadata_typeddict_constructs_with_partial_keys(th):
    """Metadata is total=False — any subset of keys constructs OK."""
    md: th.Metadata = {"name": "foo"}
    assert md["name"] == "foo"
    md2: th.Metadata = {"imdb_code": "tt0123", "runtime": "2h 0m 0s"}
    assert md2["imdb_code"] == "tt0123"


def test_result_can_carry_metadata_at_runtime(th):
    """Result rows are plain dicts at runtime; parsers attach a `metadata`
    key. The Result TypedDict doesn't formally declare it (Python 3.10
    lacks NotRequired), but runtime is permissive."""
    r = {
        "name": "x", "link": "y", "seeders": 1, "leechers": 0,
        "size": "1G", "ratio": "inf", "magnet": "magnet:?",
        "metadata": {"name": "x"},
    }
    assert r["metadata"]["name"] == "x"


# --- _https_get redirect handling ---------------------------------------

def _mk_resp(status, location=None):
    """Build a fake `requests.Response`-shaped object for redirect tests."""
    from unittest.mock import MagicMock
    r = MagicMock()
    r.status_code = status
    r.headers = {"Location": location} if location else {}
    return r


def test_https_get_refuses_non_https_initial_url(th):
    import pytest
    import requests
    with pytest.raises(requests.exceptions.InvalidURL, match="non-https"):
        th.sources.base._https_get("http://example.com/api")


def test_https_get_rewrites_http_redirect_target_to_https(th):
    """Server returns 302 with Location: http://...  — must rewrite to
    https:// before following so the next request never goes over plaintext.
    Models the exact thepiratebay.org redirect chain that was leaking
    requests onto port 80."""
    from unittest.mock import patch
    seen_urls = []

    def fake_get(url, **kwargs):
        seen_urls.append(url)
        # Caller MUST be using allow_redirects=False so we drive the loop
        assert kwargs.get("allow_redirects") is False
        if url.startswith("https://example.com/start"):
            return _mk_resp(302, location="http://example.com/landing")
        if url.startswith("https://example.com/landing"):
            return _mk_resp(200)
        raise AssertionError(f"unexpected URL: {url}")

    with patch("torrent_hound.sources.base._requests.get", side_effect=fake_get):
        r = th.sources.base._https_get("https://example.com/start")

    # Two requests in total: the original https start and the rewritten https landing
    assert len(seen_urls) == 2
    assert seen_urls[0] == "https://example.com/start"
    assert seen_urls[1] == "https://example.com/landing"  # http:// rewritten to https://
    assert all(u.startswith("https://") for u in seen_urls)
    assert r.status_code == 200


def test_https_get_follows_https_redirect_unchanged(th):
    from unittest.mock import patch
    seen = []

    def fake_get(url, **kwargs):
        seen.append(url)
        if "/a" in url:
            return _mk_resp(301, location="https://example.com/b")
        return _mk_resp(200)

    with patch("torrent_hound.sources.base._requests.get", side_effect=fake_get):
        th.sources.base._https_get("https://example.com/a")

    assert seen == ["https://example.com/a", "https://example.com/b"]


def test_https_get_refuses_non_http_scheme_redirect(th):
    """A redirect to file:// or ftp:// must be refused, not silently followed
    or rewritten — only http/https are valid downgrade vectors we know how
    to handle."""
    from unittest.mock import patch

    import pytest
    import requests

    def fake_get(url, **kwargs):
        return _mk_resp(302, location="ftp://example.com/data")

    with patch("torrent_hound.sources.base._requests.get", side_effect=fake_get):
        with pytest.raises(requests.exceptions.InvalidURL, match="non-https"):
            th.sources.base._https_get("https://example.com/")


def test_https_get_detects_redirect_loop(th):
    from unittest.mock import patch

    import pytest
    import requests

    def fake_get(url, **kwargs):
        # /a redirects to /b, /b redirects to /a — classic loop
        next_url = "https://example.com/b" if url.endswith("/a") else "https://example.com/a"
        return _mk_resp(302, location=next_url)

    with patch("torrent_hound.sources.base._requests.get", side_effect=fake_get):
        with pytest.raises(requests.TooManyRedirects):
            th.sources.base._https_get("https://example.com/a")
