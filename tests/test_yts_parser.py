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


def test_build_yts_magnet_format(th):
    magnet = th._build_yts_magnet("ABC123", "Test Movie (2024)")
    assert magnet.startswith("magnet:?xt=urn:btih:ABC123")
    assert "dn=Test+Movie" in magnet
    assert "tr=udp://" in magnet
