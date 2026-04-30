"""Tests for the YTS JSON parser.

These run offline against a captured fixture — if the YTS API changes its
response shape, these tests will catch it.
"""


def test_parse_yts_json_returns_results(th, yts_interstellar_json):
    results = th._parse_yts_json(yts_interstellar_json)
    assert len(results) > 0


def test_parse_yts_json_respects_limit(th, yts_interstellar_json):
    results = th._parse_yts_json(yts_interstellar_json, limit=2)
    assert len(results) == 2


def test_parse_yts_json_each_result_has_required_fields(th, yts_interstellar_json):
    required = {"name", "link", "seeders", "leechers", "magnet", "size", "ratio"}
    for r in th._parse_yts_json(yts_interstellar_json):
        assert required.issubset(r.keys()), f"missing fields in {r}"


def test_parse_yts_json_magnet_starts_with_magnet_scheme(th, yts_interstellar_json):
    for r in th._parse_yts_json(yts_interstellar_json):
        assert r["magnet"].startswith("magnet:?"), r["magnet"]


def test_parse_yts_json_name_includes_quality(th, yts_interstellar_json):
    for r in th._parse_yts_json(yts_interstellar_json):
        assert "[" in r["name"] and "]" in r["name"], f"no quality tag in {r['name']}"


def test_parse_yts_json_seeders_and_leechers_are_ints(th, yts_interstellar_json):
    for r in th._parse_yts_json(yts_interstellar_json):
        assert isinstance(r["seeders"], int)
        assert isinstance(r["leechers"], int)


def test_parse_yts_json_empty_on_no_movies(th):
    assert th._parse_yts_json({}) == []
    assert th._parse_yts_json({"data": {}}) == []
    assert th._parse_yts_json({"data": {"movies": None}}) == []
    assert th._parse_yts_json({"data": {"movies": []}}) == []


def test_extract_yts_quality_pulls_token(th):
    assert th._extract_yts_quality("the matrix 1080p") == ("the matrix", "1080p")
    assert th._extract_yts_quality("matrix 720p") == ("matrix", "720p")
    assert th._extract_yts_quality("matrix 2160p") == ("matrix", "2160p")


def test_extract_yts_quality_no_token_when_query_is_plain(th):
    assert th._extract_yts_quality("the matrix") == ("the matrix", None)
    assert th._extract_yts_quality("foo bar baz") == ("foo bar baz", None)
    assert th._extract_yts_quality("") == ("", None)


def test_extract_yts_quality_is_case_insensitive(th):
    # User typing 1080P (or even mixed) should be normalised to YTS's '1080p'.
    assert th._extract_yts_quality("foo 1080P") == ("foo", "1080p")
    assert th._extract_yts_quality("FOO 720P") == ("FOO", "720p")


def test_extract_yts_quality_normalises_3d_to_canonical(th):
    # YTS expects literal '3D' on the wire even though we accept lowercase.
    assert th._extract_yts_quality("foo 3d") == ("foo", "3D")
    assert th._extract_yts_quality("foo 3D") == ("foo", "3D")


def test_extract_yts_quality_handles_multi_token_x265(th):
    assert th._extract_yts_quality("foo 1080p.x265") == ("foo", "1080p.x265")


def test_extract_yts_quality_unknown_quality_left_in_query(th):
    # Unknown quality tokens (not in YTS's enum) stay in the query so the
    # API can decide. We don't try to invent a quality that doesn't exist.
    assert th._extract_yts_quality("matrix 9999p") == ("matrix 9999p", None)


def test_parse_yts_json_does_not_rewrite_url_when_served_by_api_host(th, yts_interstellar_json):
    """When the request was served by movies-api.accel.li (the API-only host
    per YTS's own docs), the URL must NOT be rewritten to that host — accel.li
    doesn't serve movie pages, so rewriting would produce a link that returns
    JSON instead of a viewable page. The API's returned `url` (e.g.
    `https://yts.bz/movies/...`) is canonical and must pass through intact."""
    results = th._parse_yts_json(yts_interstellar_json, domain="movies-api.accel.li", limit=5)
    assert len(results) > 0
    for r in results:
        assert "movies-api.accel.li" not in r["link"], f"link wrongly rewritten to API host: {r['link']}"
        # Still expect a real YTS page URL
        assert r["link"].startswith("https://"), f"link not absolute: {r['link']}"


def test_parse_yts_json_does_rewrite_url_when_served_by_mirror(th, yts_interstellar_json):
    """Sanity check the existing behaviour for non-API hosts is preserved: URLs
    get rewritten to the responding mirror so dead-mirror redirects don't
    poison links."""
    results = th._parse_yts_json(yts_interstellar_json, domain="yts.bz", limit=5)
    assert len(results) > 0
    for r in results:
        assert "yts.bz" in r["link"], f"expected link rewritten to yts.bz: {r['link']}"


def test_parse_yts_json_quality_filter_drops_other_variants(th, yts_interstellar_json):
    # Without filter: every quality variant for every movie.
    all_results = th._parse_yts_json(yts_interstellar_json, limit=50)
    qualities_present = {r["name"].rsplit("[", 1)[1].rstrip("]") for r in all_results}
    assert len(qualities_present) > 1, "fixture should have multiple quality variants"

    # With quality_filter='1080p': only 1080p rows survive.
    only_1080p = th._parse_yts_json(yts_interstellar_json, limit=50, quality_filter="1080p")
    assert len(only_1080p) > 0, "fixture should contain at least one 1080p variant"
    for r in only_1080p:
        assert r["name"].endswith("[1080p]"), f"unexpected quality in {r['name']}"


def test_build_yts_magnet_format(th):
    magnet = th._build_yts_magnet("ABC123", "Test Movie (2024)")
    assert magnet.startswith("magnet:?xt=urn:btih:ABC123")
    assert "dn=Test+Movie" in magnet
    assert "tr=udp://" in magnet
