"""Tests for the switch() command dispatcher and its helpers.

These focus on the regex-based routing — the footgun the old substring
dispatcher had. We verify that 'cs5' routes to the cs handler (not c), that
invalid numbers are rejected, and that the bounds check works.
"""
from unittest.mock import patch


def _fake_results(n=5):
    return [
        {
            "name": f"result {i}",
            "link": f"https://example.invalid/t/{i}",
            "magnet": f"magnet:?xt=urn:btih:fake{i}",
            "seeders": 10,
            "leechers": 1,
            "size": "1 GiB",
            "ratio": "10.0",
        }
        for i in range(1, n + 1)
    ]


def test_get_entry_valid_index(th):
    th.results = _fake_results(5)
    th.num_results = 5
    entry = th._get_entry(3)
    assert entry["name"] == "result 3"


def test_get_entry_out_of_range(th):
    th.results = _fake_results(5)
    th.num_results = 5
    assert th._get_entry(0) is None
    assert th._get_entry(6) is None
    assert th._get_entry(-1) is None


def test_switch_m_prints_magnet(th, capsys):
    th.results = _fake_results(3)
    th.num_results = 3
    th.switch("m2")
    out = capsys.readouterr().out
    assert "magnet:?xt=urn:btih:fake2" in out


def test_switch_c_copies_magnet_to_clipboard(th):
    th.results = _fake_results(3)
    th.num_results = 3
    with patch.object(th, "pyperclip") as pc:
        th.switch("c1")
        pc.copy.assert_called_once_with("magnet:?xt=urn:btih:fake1")


def test_switch_cs_routes_to_cs_not_c(th):
    """The old substring dispatcher was vulnerable to 'cs' being mis-routed
    to 'c'. The regex dispatcher must route cs<n> to the cs handler, which
    both copies AND opens seedr."""
    th.results = _fake_results(3)
    th.num_results = 3
    with patch.object(th, "pyperclip") as pc, patch.object(th, "webbrowser") as wb:
        th.switch("cs2")
        pc.copy.assert_called_once_with("magnet:?xt=urn:btih:fake2")
        wb.open.assert_called_once_with("https://www.seedr.cc", new=2)


def test_switch_o_opens_torrent_page(th):
    th.results = _fake_results(3)
    th.num_results = 3
    with patch.object(th, "webbrowser") as wb:
        th.switch("o1")
        wb.open.assert_called_once_with("https://example.invalid/t/1", new=2)


def test_switch_d_sends_magnet_to_default_client(th):
    th.results = _fake_results(3)
    th.num_results = 3
    with patch.object(th, "webbrowser") as wb:
        th.switch("d3")
        wb.open.assert_called_once_with("magnet:?xt=urn:btih:fake3", new=2)


def test_switch_invalid_index_prints_error(th, capsys):
    th.results = _fake_results(3)
    th.num_results = 3
    th.switch("m99")
    assert "Invalid command" in capsys.readouterr().out


def test_switch_unknown_command_prints_invalid(th, capsys):
    th.switch("zzz")
    assert "Invalid command" in capsys.readouterr().out


def test_switch_q_sets_exit(th):
    th.exit = False
    th.switch("q")
    assert th.exit is True


def test_switch_u_shows_all_source_urls(th, capsys):
    """The u command should show URLs for every source that returned results."""
    th.tpb_url = "https://thepiratebay.zone/s/?q=test"
    th.yts_url = "https://yts.lt/api/v2/list_movies.json?query_term=test"
    th.eztv_url = "https://eztvx.to/api/get-torrents?imdb_id=12345"
    th.switch("u")
    out = capsys.readouterr().out
    assert "PirateBay" in out
    assert "YTS" in out
    assert "EZTV" in out
    assert "thepiratebay.zone" in out
    assert "yts.lt" in out
    assert "eztvx.to" in out


def test_switch_u_skips_empty_urls(th, capsys):
    """Sources that didn't run shouldn't appear in u output."""
    th.tpb_url = "https://thepiratebay.zone/s/?q=test"
    th.yts_url = ""
    th.eztv_url = ""
    th.switch("u")
    out = capsys.readouterr().out
    assert "PirateBay" in out
    assert "YTS" not in out
    assert "EZTV" not in out


def test_remove_and_replace_spaces(th):
    assert th.removeAndReplaceSpaces("hello world") == "hello+world"
    assert th.removeAndReplaceSpaces(" leading space") == "leading+space"
    assert th.removeAndReplaceSpaces("no_space") == "no_space"


def test_switch_rd_routes_to_cmd_rd(th):
    th.results = _fake_results(5)
    th.num_results = 5
    with patch.object(th, "_cmd_rd") as m_rd:
        th.switch("rd3")
    m_rd.assert_called_once()
    # Should have received entry for index 3
    assert m_rd.call_args.args[0]["name"] == "result 3"


def test_switch_rd0_rejected_as_invalid(th, capsys):
    th.results = _fake_results(5)
    th.num_results = 5
    th.switch("rd0")
    out = capsys.readouterr().out
    assert "Invalid command" in out
