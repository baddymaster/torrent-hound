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


def test_fmt_runtime_minutes_only(th):
    # 30 minutes
    assert th._fmt_runtime(1800) == "0h 30m 0s"


def test_fmt_runtime_seconds_only(th):
    assert th._fmt_runtime(45) == "0h 0m 45s"


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
