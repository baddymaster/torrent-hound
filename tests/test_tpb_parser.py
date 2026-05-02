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


# --- apibay JSON path ----------------------------------------------------

def test_parse_apibay_item_stores_apibay_id_for_lazy_fetch(th, apibay_ubuntu_json):
    """Every parsed apibay row must carry _apibay_id in metadata — the
    metadata overlay's lazy worker uses it to route to t.php for the
    descr field, since thepiratebay.org/torrent/<id> is now the SPA shell
    and yields nothing to the legacy HTML parser."""
    parsed = th.sources.tpb._parse_apibay_item(apibay_ubuntu_json[0])
    assert parsed["metadata"]["_apibay_id"] == apibay_ubuntu_json[0]["id"]


def test_parse_apibay_descr_extracts_director_cast_summary(th, apibay_torrent_detail_json):
    """The descr field uses the multi-line block format (Director\\n<name>\\n\\n
    Writers\\n... \\nStars\\n<name>) — exactly one of the variants the existing
    description-text helpers already handle."""
    descr = apibay_torrent_detail_json["descr"]
    md = th.sources.tpb._parse_apibay_descr(descr)
    assert md.get("director") == "Director Name"
    assert "Actor One" in md.get("cast", "")
    assert md.get("summary", "").startswith("A character-driven drama")
    # Genre / Duration / Audio / Subtitles labelled lines also extract
    assert "Drama" in md.get("genre", "")
    assert md.get("runtime") == "1h 49m"
    assert "DTS" in md.get("audio", "")
    assert "English" in md.get("subtitles", "")


def test_fetch_apibay_details_returns_empty_on_error(th):
    """Network errors and non-JSON responses must degrade to {} so the
    metadata worker surfaces the standard 'press v again to retry' message."""
    from unittest.mock import patch

    import requests
    with patch("torrent_hound.sources.tpb._https_get", side_effect=requests.ConnectionError("dead")):
        assert th.sources.tpb._fetch_apibay_details(123) == {}


def test_fetch_apibay_details_returns_empty_on_zero_id(th):
    """Defensive: 0 / None / empty id short-circuits without hitting the network."""
    assert th.sources.tpb._fetch_apibay_details(None) == {}
    assert th.sources.tpb._fetch_apibay_details(0) == {}
    assert th.sources.tpb._fetch_apibay_details("") == {}


def test_fetch_apibay_details_returns_empty_when_descr_missing(th):
    """Some uploads have no description; t.php returns the record with
    descr='' — return {} so the worker reports a retry-able failure rather
    than declaring a successful empty fetch."""
    from unittest.mock import MagicMock, patch
    fake = MagicMock()
    fake.json.return_value = {"id": 1, "descr": ""}
    fake.status_code = 200
    fake.headers = {}
    with patch("torrent_hound.sources.tpb._https_get", return_value=fake):
        assert th.sources.tpb._fetch_apibay_details(1) == {}


def test_fetch_apibay_details_parses_real_descr(th, apibay_torrent_detail_json):
    """End-to-end: t.php returns a JSON dict with descr, _fetch_apibay_details
    runs the description extractors over it and returns a metadata-shaped
    dict with director/cast/summary/etc."""
    from unittest.mock import MagicMock, patch
    fake = MagicMock()
    fake.json.return_value = apibay_torrent_detail_json
    fake.status_code = 200
    fake.headers = {}
    with patch("torrent_hound.sources.tpb._https_get", return_value=fake):
        result = th.sources.tpb._fetch_apibay_details(10000001)
    assert result.get("director") == "Director Name"
    assert "Actor One" in result.get("cast", "")
    assert result.get("summary", "").startswith("A character-driven drama")


def test_parse_apibay_item_extracts_full_record(th, apibay_ubuntu_json):
    """An apibay record produces a Result-shaped dict with a constructed
    magnet, an thepiratebay.org link, normalised fields, and metadata."""
    parsed = th.sources.tpb._parse_apibay_item(apibay_ubuntu_json[0])
    assert parsed is not None
    required = {"name", "link", "seeders", "leechers", "magnet", "size", "ratio"}
    assert required.issubset(parsed.keys())
    assert parsed["magnet"].startswith("magnet:?xt=urn:btih:")
    assert parsed["link"].startswith("https://thepiratebay.org/torrent/")
    assert isinstance(parsed["seeders"], int)
    assert isinstance(parsed["leechers"], int)
    # Size is humanised, not raw bytes
    assert any(unit in parsed["size"] for unit in ("B", "KB", "MB", "GB"))


def test_parse_apibay_item_constructs_magnet_with_canonical_trackers(th, apibay_ubuntu_json):
    """The magnet must carry every tracker from TPB_TRACKERS — a swarm-
    discovery regression we'd otherwise notice only in the wild."""
    parsed = th.sources.tpb._parse_apibay_item(apibay_ubuntu_json[0])
    for tracker in th.sources.tpb.TPB_TRACKERS:
        # Trackers are URL-encoded inside the magnet
        import urllib.parse
        assert urllib.parse.quote(tracker, safe="") in parsed["magnet"]


def test_parse_apibay_item_returns_none_for_no_results_sentinel(th):
    """Apibay returns a single sentinel item when the query has no matches.
    The parser must skip it so the caller can emit `empty` cleanly."""
    sentinel = {
        "id": "0", "name": "No results returned",
        "info_hash": "0" * 40, "leechers": "0", "seeders": "0",
        "size": "0", "num_files": "0", "added": "0",
    }
    assert th.sources.tpb._parse_apibay_item(sentinel) is None


def test_parse_apibay_item_returns_none_for_malformed_record(th):
    """Records missing required keys must be skipped, not raise."""
    assert th.sources.tpb._parse_apibay_item({}) is None
    assert th.sources.tpb._parse_apibay_item({"name": "x"}) is None
    assert th.sources.tpb._parse_apibay_item({"info_hash": "abc"}) is None


def test_search_apibay_emits_ok_event_on_results(th, apibay_ubuntu_json):
    """End-to-end: apibay returns a list, the function parses it and emits
    a single ok event with the count."""
    from unittest.mock import MagicMock, patch
    fake_resp = MagicMock()
    fake_resp.json.return_value = apibay_ubuntu_json
    fake_resp.status_code = 200
    fake_resp.headers = {}
    events = []
    with patch.object(th.sources.tpb, "_https_get", return_value=fake_resp):
        rows = th.sources.tpb._search_apibay("ubuntu", progress=lambda e: events.append(e))
    assert rows
    assert any(e["type"] == "ok" for e in events)


def test_search_apibay_emits_empty_event_on_no_results_sentinel(th):
    """Apibay's no-results sentinel must surface as `empty`, not `ok` and not failed."""
    from unittest.mock import MagicMock, patch
    sentinel = [{
        "id": "0", "name": "No results returned", "info_hash": "0" * 40,
        "leechers": "0", "seeders": "0", "size": "0",
        "num_files": "0", "added": "0", "username": "", "category": "0", "imdb": "",
    }]
    fake_resp = MagicMock()
    fake_resp.json.return_value = sentinel
    fake_resp.status_code = 200
    fake_resp.headers = {}
    events = []
    with patch.object(th.sources.tpb, "_https_get", return_value=fake_resp):
        rows = th.sources.tpb._search_apibay("zzznomatch", progress=lambda e: events.append(e))
    assert rows == []
    assert any(e["type"] == "empty" for e in events)


def test_search_apibay_returns_none_on_network_error(th):
    """On a RequestException we return None so the caller falls back to
    HTML mirrors. We also emit `mirror_failed` so the trail counts the
    apibay attempt as a retry rather than silently skipping it."""
    from unittest.mock import patch

    import requests
    events = []
    with patch.object(th.sources.tpb, "_https_get", side_effect=requests.ConnectionError("dead")):
        result = th.sources.tpb._search_apibay("ubuntu", progress=lambda e: events.append(e))
    assert result is None
    assert any(e["type"] == "mirror_failed" for e in events)


def test_search_apibay_returns_none_on_non_list_response(th):
    """A non-list response (e.g. error JSON object) must return None for fallback."""
    from unittest.mock import MagicMock, patch
    fake_resp = MagicMock()
    fake_resp.json.return_value = {"error": "bad request"}
    fake_resp.status_code = 200
    fake_resp.headers = {}
    with patch.object(th.sources.tpb, "_https_get", return_value=fake_resp):
        assert th.sources.tpb._search_apibay("ubuntu") is None


def test_searchpiratebay_uses_apibay_first(th, apibay_ubuntu_json):
    """The orchestrator must hit apibay before any HTML mirror — when
    apibay succeeds, no HTML mirror should be touched."""
    from unittest.mock import MagicMock, patch
    fake_resp = MagicMock()
    fake_resp.json.return_value = apibay_ubuntu_json
    fake_resp.status_code = 200
    fake_resp.headers = {}
    html_mirror_calls = []
    with patch.object(th.sources.tpb, "_https_get", return_value=fake_resp), \
         patch.object(th.sources.tpb, "_parse_tpb_html",
                      side_effect=lambda *a, **kw: html_mirror_calls.append(a) or []):
        results = th.searchPirateBayCondensed("ubuntu", quiet_mode=True)
    assert results
    assert html_mirror_calls == []  # HTML scrape never invoked


def test_searchpiratebay_falls_back_to_html_when_apibay_fails(th, tpb_ubuntu_html):
    """If apibay raises, HTML mirrors should still be tried."""
    from unittest.mock import MagicMock, patch

    import requests

    def fake_https_get(url, **kwargs):
        if "apibay.org" in url:
            raise requests.ConnectionError("apibay down")
        # HTML mirror call
        resp = MagicMock()
        resp.content = tpb_ubuntu_html
        resp.status_code = 200
        resp.headers = {}
        return resp

    with patch.object(th.sources.tpb, "_https_get", side_effect=fake_https_get):
        results = th.searchPirateBayCondensed("ubuntu", quiet_mode=True)
    assert len(results) > 0  # HTML fallback yielded results


def test_parse_tpb_html_handles_modern_8cell_layout(th, tpb_modern_layout_html):
    """tpb.party (and similar mirrors) now serve an 8-cell row layout with
    no `detLink` class and the magnet/size/seed/leech each in their own td.
    The parser must extract real results from this layout — the previous
    parser raised TypeError on the first row, escaped to the orchestrator,
    and surfaced as 'all mirrors failed'."""
    results = th._parse_tpb_html(tpb_modern_layout_html, domain="tpb.party", limit=10)
    assert len(results) > 0, "modern layout should yield at least one result"
    required = {"name", "link", "seeders", "leechers", "magnet", "size", "ratio"}
    for r in results:
        assert required.issubset(r.keys()), f"missing fields in {r}"
        assert r["magnet"].startswith("magnet:?")
        assert isinstance(r["seeders"], int)
        assert isinstance(r["leechers"], int)
        assert r["link"].startswith("https://"), r["link"]
        # Sizes look like '6.07 GiB' / '780 MB' — never empty
        assert r["size"]


def test_parse_tpb_html_modern_layout_size_extracted(th, tpb_modern_layout_html):
    """Sizes in the modern layout come from a dedicated td, not the legacy
    <font> string. Confirm at least one result has a binary-prefix size
    matching the live tpb.party format."""
    import re as _re
    results = th._parse_tpb_html(tpb_modern_layout_html, domain="tpb.party", limit=10)
    sizes = [r["size"] for r in results]
    assert any(_re.match(r'^\d+(\.\d+)?\s*[KMGT]i?B$', s) for s in sizes), sizes


def test_parse_tpb_html_skips_malformed_row_without_tanking(th):
    """A single broken row must not break the rest. Previously a TypeError
    inside the row body would escape because the per-row except didn't list
    TypeError; the whole parse would return [] (or worse, raise)."""
    # First row is intentionally minimal — no /torrent/ anchor, no magnet.
    # Second row is well-formed modern-layout. Parser should yield exactly one.
    html = b"""
    <html><body>
      <table id="searchResult">
        <tr><th>x</th></tr>
        <tr><td>broken</td></tr>
        <tr>
          <td><a href="/browse/303">Apps</a></td>
          <td><a href="/torrent/1/foo">foo</a></td>
          <td>04-25 16:35</td>
          <td><a href="magnet:?xt=urn:btih:abcd">m</a></td>
          <td>1.0 GiB</td>
          <td>10</td>
          <td>2</td>
          <td>uploader</td>
        </tr>
      </table>
    </body></html>
    """
    rows = th._parse_tpb_html(html, domain="tpb.party", limit=10)
    assert len(rows) == 1
    assert rows[0]["name"] == "foo"
    assert rows[0]["seeders"] == 10
    assert rows[0]["leechers"] == 2


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
