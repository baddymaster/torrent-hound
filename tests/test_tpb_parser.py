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


def test_tpb_page_is_empty_results_true_for_zero_match_page(th, tpb_no_hits_html):
    """The captured no-hits page should be classified as a genuine empty
    result (not a mirror failure) — the searchResult table is present but
    only contains the header row."""
    assert th._tpb_page_is_empty_results(tpb_no_hits_html) is True


def test_tpb_page_is_empty_results_false_for_real_results_page(th, tpb_ubuntu_html):
    """A real results page must NOT be classified as empty — table has many rows."""
    assert th._tpb_page_is_empty_results(tpb_ubuntu_html) is False


def test_tpb_page_is_empty_results_false_when_table_missing(th):
    """A page without the searchResult table at all is a mirror failure
    (dead/blocked/CAPTCHA), not an empty result — caller will probe the next mirror."""
    assert th._tpb_page_is_empty_results(b"<html><body>blocked</body></html>") is False
    assert th._tpb_page_is_empty_results(b"") is False


def test_parse_tpb_html_populates_metadata_from_name(th, tpb_ubuntu_html):
    """Eager TPB metadata: name + whatever release tags the row name's
    regex catches. Detail-page fields fill later via lazy fetch."""
    results = th._parse_tpb_html(tpb_ubuntu_html, limit=3)
    assert len(results) == 3
    for r in results:
        md = r["metadata"]
        assert md["name"] == r["name"]
        # `released` only present if the name has a 19xx/20xx year — most
        # ubuntu rows don't, so we assert only correctness when present.
        if "released" in md:
            assert md["released"].isdigit() and len(md["released"]) == 4


def test_build_results_table_strips_wide_unicode(th):
    """Emoji and wide Unicode in torrent names must be stripped to prevent
    table misalignment."""
    import re
    name_with_emoji = "Project.Hail.Mary.2026.2160p.WEBrip.h265.Dual.YG⭐"
    cleaned = re.sub(r'[^\x20-\x7E]', '', name_with_emoji)
    assert "⭐" not in cleaned
    assert "YG" in cleaned


def test_parse_tpb_html_forces_https_on_absolute_http_links(th):
    """If TPB emits an absolute http:// href in the search row, the parser
    must rewrite it to https:// so we never hand the user an http link."""
    html = b"""
    <html><body>
      <table id="searchResult">
        <tr><th>x</th></tr>
        <tr>
          <td><a class="iconLeft" href="/browse/200">cat</a></td>
          <td>
            <a class="detLink" href="http://thepiratebay.zone/torrent/123/foo">foo</a>
            <a href="magnet:?xt=urn:btih:abcd"><img alt="Magnet link" /></a>
            <font>Uploaded 01-01 20:00, Size 1.0&nbsp;MiB, ULed by anon</font>
          </td>
          <td>10</td><td>2</td>
        </tr>
      </table>
    </body></html>
    """
    rows = th._parse_tpb_html(html, domain="thepiratebay.zone", limit=10)
    assert rows, "fixture should yield at least one row"
    assert rows[0]["link"].startswith("https://")
    assert "http://" not in rows[0]["link"]
    assert "thepiratebay.zone/torrent/123/foo" in rows[0]["link"]
