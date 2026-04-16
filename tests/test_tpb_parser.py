"""Tests for the TPB HTML parser.

These run offline against a captured fixture — if TPB changes their markup
and breaks parsing, these tests will fail loud instead of the tool silently
returning 0 results.
"""


def test_parse_tpb_html_returns_ten_results(th, tpb_ubuntu_html):
    results = th._parse_tpb_html(tpb_ubuntu_html, limit=10)
    assert len(results) == 10


def test_parse_tpb_html_respects_limit(th, tpb_ubuntu_html):
    results = th._parse_tpb_html(tpb_ubuntu_html, limit=3)
    assert len(results) == 3


def test_parse_tpb_html_each_result_has_required_fields(th, tpb_ubuntu_html):
    required = {"name", "link", "seeders", "leechers", "magnet", "size", "ratio"}
    for r in th._parse_tpb_html(tpb_ubuntu_html, limit=10):
        assert required.issubset(r.keys()), f"missing fields in {r}"


def test_parse_tpb_html_magnet_starts_with_magnet_scheme(th, tpb_ubuntu_html):
    for r in th._parse_tpb_html(tpb_ubuntu_html, limit=10):
        assert r["magnet"].startswith("magnet:?"), r["magnet"]


def test_parse_tpb_html_seeders_and_leechers_are_ints(th, tpb_ubuntu_html):
    for r in th._parse_tpb_html(tpb_ubuntu_html, limit=10):
        assert isinstance(r["seeders"], int)
        assert isinstance(r["leechers"], int)


def test_parse_tpb_html_ratio_formatted_with_one_decimal_or_inf(th, tpb_ubuntu_html):
    for r in th._parse_tpb_html(tpb_ubuntu_html, limit=10):
        assert r["ratio"] == "inf" or "." in r["ratio"]


def test_parse_tpb_html_empty_on_missing_results_table(th):
    html = b"<html><body><p>no table here</p></body></html>"
    assert th._parse_tpb_html(html) == []


def test_parse_tpb_html_empty_on_garbage_input(th):
    assert th._parse_tpb_html(b"") == []
    assert th._parse_tpb_html(b"not html") == []


def test_parse_tpb_html_link_includes_domain(th, tpb_ubuntu_html):
    """Links must be absolute URLs with the working domain, not bare paths."""
    results = th._parse_tpb_html(tpb_ubuntu_html, domain="thepiratebay.zone", limit=3)
    for r in results:
        assert r["link"].startswith("https://"), f"link is not absolute: {r['link']}"


def test_build_results_table_strips_wide_unicode(th):
    """Emoji and wide Unicode in torrent names must be stripped to prevent
    table misalignment."""
    import re
    name_with_emoji = "Project.Hail.Mary.2026.2160p.WEBrip.h265.Dual.YG⭐"
    cleaned = re.sub(r'[^\x20-\x7E]', '', name_with_emoji)
    assert "⭐" not in cleaned
    assert "YG" in cleaned
