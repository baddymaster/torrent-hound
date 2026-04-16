"""Tests for the Real-Debrid integration helpers in torrent_hound.py."""
import socket
from unittest.mock import MagicMock, patch

import pytest

# --- Hash extraction -----------------------------------------------------

def test_parse_hash_hex_40(th):
    magnet = "magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567&dn=foo"
    assert th._rd_parse_hash(magnet) == "0123456789abcdef0123456789abcdef01234567"


def test_parse_hash_hex_uppercase_lowercased(th):
    magnet = "magnet:?xt=urn:btih:0123456789ABCDEF0123456789ABCDEF01234567"
    assert th._rd_parse_hash(magnet) == "0123456789abcdef0123456789abcdef01234567"


def test_parse_hash_base32_decoded_to_hex(th):
    # base32 of a known 20-byte hash: b"\x01" * 20 encodes to "AEAQCAIBAEAQCAIBAEAQCAIBAEAQCAIB"
    magnet = "magnet:?xt=urn:btih:AEAQCAIBAEAQCAIBAEAQCAIBAEAQCAIB&dn=foo"
    assert th._rd_parse_hash(magnet) == "01" * 20


def test_parse_hash_malformed_returns_none(th):
    assert th._rd_parse_hash("magnet:?dn=no-hash-here") is None
    assert th._rd_parse_hash("not a magnet") is None
    assert th._rd_parse_hash("") is None


# --- Human size ----------------------------------------------------------

@pytest.mark.parametrize("n,expected", [
    (0, "0 B"),
    (512, "512 B"),
    (1024, "1.0 KB"),
    (1536, "1.5 KB"),
    (1024 * 1024, "1.0 MB"),
    (int(2.1 * 1024**3), "2.1 GB"),
    (int(1.4 * 1024**4), "1.4 TB"),
    (28 * 1024, "28.0 KB"),
])
def test_human_size(th, n, expected):
    assert th._human_size(n) == expected


# --- Selection parser ----------------------------------------------------

@pytest.mark.parametrize("text,total,expected", [
    ("", 5, [1, 2, 3, 4, 5]),
    ("all", 5, [1, 2, 3, 4, 5]),
    ("ALL", 5, [1, 2, 3, 4, 5]),
    ("  all  ", 5, [1, 2, 3, 4, 5]),
    ("3", 5, [3]),
    ("1,3,5", 5, [1, 3, 5]),
    ("5,1,3", 5, [1, 3, 5]),          # sorted, deduped
    ("1,1,1", 5, [1]),
    ("1-3", 5, [1, 2, 3]),
    ("1-5", 5, [1, 2, 3, 4, 5]),
    ("1,3-5,2", 5, [1, 2, 3, 4, 5]),
    ("  1 , 3 - 5 ", 5, [1, 3, 4, 5]),
])
def test_parse_selection_valid(th, text, total, expected):
    assert th._rd_parse_selection(text, total) == expected


def test_parse_selection_cancel(th):
    assert th._rd_parse_selection("c", 5) == "cancel"
    assert th._rd_parse_selection("  C  ", 5) == "cancel"


@pytest.mark.parametrize("text", [
    "0",          # out of range (1-indexed)
    "6",          # out of range when total=5
    "1-6",        # end out of range
    "0-2",        # start out of range
    "3-1",        # reverse range
    "abc",
    "1,,3",
    "1-",
    "-3",
    "1-3-5",
])
def test_parse_selection_invalid_returns_none(th, text):
    assert th._rd_parse_selection(text, 5) is None


# --- Error classification / request wrapper ------------------------------


def _mk_response(status, headers=None, json_body=None):
    r = MagicMock()
    r.status_code = status
    r.headers = headers or {}
    r.json.return_value = json_body or {}
    return r


def test_rd_request_dns_failure_classified(th):
    err = requests_ConnectionError_with_gaierror()
    with patch.object(th.requests, "request", side_effect=err):
        with pytest.raises(th._RdError) as exc:
            th._rd_request("GET", "/x", token="t")
    assert "DNS lookup" in str(exc.value)
    assert "VPN" in str(exc.value)


def requests_ConnectionError_with_gaierror():
    import requests
    exc = requests.ConnectionError("Failed to establish connection")
    exc.__cause__ = socket.gaierror(-2, "Name or service not known")
    return exc


def test_rd_request_plain_connection_error(th):
    import requests
    err = requests.ConnectionError("connection refused")
    with patch.object(th.requests, "request", side_effect=err):
        with pytest.raises(th._RdError) as exc:
            th._rd_request("GET", "/x", token="t")
    assert "Couldn't reach" in str(exc.value)
    assert "DNS" not in str(exc.value)


def test_rd_request_timeout(th):
    import requests
    with patch.object(th.requests, "request", side_effect=requests.Timeout()):
        with pytest.raises(th._RdError) as exc:
            th._rd_request("GET", "/x", token="t")
    assert "timed out" in str(exc.value)


def test_rd_request_401(th):
    with patch.object(th.requests, "request", return_value=_mk_response(401)):
        with pytest.raises(th._RdError) as exc:
            th._rd_request("GET", "/x", token="bad")
    assert "rejected the token" in str(exc.value)


def test_rd_request_403_with_cdn_markers(th):
    resp = _mk_response(403, headers={"cf-ray": "abc", "server": "cloudflare"})
    with patch.object(th.requests, "request", return_value=resp):
        with pytest.raises(th._RdError) as exc:
            th._rd_request("GET", "/x", token="t")
    assert "block page" in str(exc.value)
    assert "VPN" in str(exc.value)


def test_rd_request_403_no_cdn_markers(th):
    resp = _mk_response(403, headers={"server": "nginx"})
    with patch.object(th.requests, "request", return_value=resp):
        with pytest.raises(th._RdError) as exc:
            th._rd_request("GET", "/x", token="t")
    assert "403" in str(exc.value)
    assert "quota" in str(exc.value)


def test_rd_request_429(th):
    with patch.object(th.requests, "request", return_value=_mk_response(429)):
        with pytest.raises(th._RdError) as exc:
            th._rd_request("GET", "/x", token="t")
    assert "rate limit" in str(exc.value)


def test_rd_request_451(th):
    with patch.object(th.requests, "request", return_value=_mk_response(451)):
        with pytest.raises(th._RdError) as exc:
            th._rd_request("GET", "/x", token="t")
    assert "geo-blocked" in str(exc.value)


def test_rd_request_500(th):
    with patch.object(th.requests, "request", return_value=_mk_response(500)):
        with pytest.raises(th._RdError) as exc:
            th._rd_request("GET", "/x", token="t")
    assert "500" in str(exc.value)


def test_rd_request_happy_path_returns_json(th):
    resp = _mk_response(200, json_body={"ok": True})
    with patch.object(th.requests, "request", return_value=resp) as m:
        body = th._rd_request("GET", "/x", token="secret")
    assert body == {"ok": True}
    # Auth header is set, timeout is 3s, URL is prefixed
    call = m.call_args
    assert call.kwargs["headers"]["Authorization"] == "Bearer secret"
    assert call.kwargs["timeout"] == 3
    assert call.args[1].endswith("/x")


def test_rd_request_201_returns_json(th):
    # RD's addMagnet returns 201 Created with the {id, uri} body — must be treated as success
    resp = _mk_response(201, json_body={"id": "tid", "uri": "magnet:?xt=..."})
    with patch.object(th.requests, "request", return_value=resp):
        body = th._rd_request("POST", "/torrents/addMagnet", token="t", data={"magnet": "m"})
    assert body == {"id": "tid", "uri": "magnet:?xt=..."}


def test_rd_request_204_no_content(th):
    # selectFiles returns 204 with no body — not an error
    resp = _mk_response(204)
    resp.json.side_effect = ValueError("No JSON")
    with patch.object(th.requests, "request", return_value=resp):
        assert th._rd_request("POST", "/x", token="t") is None


def test_rd_request_200_non_json_raises_rd_error(th):
    # Captive portal / transparent proxy returning HTML with HTTP 200
    resp = _mk_response(200)
    resp.json.side_effect = ValueError("Expecting value")
    with patch.object(th.requests, "request", return_value=resp):
        with pytest.raises(th._RdError) as exc:
            th._rd_request("GET", "/x", token="t")
    assert "non-JSON" in str(exc.value) or "captive portal" in str(exc.value).lower()


# --- Endpoint wrappers ---------------------------------------------------

def test_rd_check_cached_true(th):
    # RD returns non-empty {HASH: {"rd": [...]}} when cached
    cached = {"01" * 20: {"rd": [{"0": {"filename": "x.mkv"}}]}}
    with patch.object(th, "_rd_request", return_value=cached):
        assert th._rd_check_cached("01" * 20, token="t") is True


def test_rd_check_cached_false_empty_rd(th):
    # Not cached: {HASH: {"rd": []}} OR {HASH: []} OR {}
    for payload in ({"01" * 20: {"rd": []}}, {"01" * 20: []}, {}):
        with patch.object(th, "_rd_request", return_value=payload):
            assert th._rd_check_cached("01" * 20, token="t") is False


def test_rd_add_magnet_returns_id(th):
    with patch.object(th, "_rd_request", return_value={"id": "abc", "uri": "..."}) as m:
        result = th._rd_add_magnet("magnet:?xt=...", token="t")
    assert result == "abc"
    assert m.call_args.args == ("POST", "/torrents/addMagnet")
    assert m.call_args.kwargs["data"] == {"magnet": "magnet:?xt=..."}


def test_rd_select_files_all(th):
    with patch.object(th, "_rd_request", return_value=None) as m:
        th._rd_select_files("tid", "all", token="t")
    assert m.call_args.args == ("POST", "/torrents/selectFiles/tid")
    assert m.call_args.kwargs["data"] == {"files": "all"}


def test_rd_select_files_specific_ids(th):
    with patch.object(th, "_rd_request", return_value=None) as m:
        th._rd_select_files("tid", "1,3,5", token="t")
    assert m.call_args.kwargs["data"] == {"files": "1,3,5"}


def test_rd_get_info(th):
    info = {"status": "downloaded", "files": [], "links": ["l1", "l2"]}
    with patch.object(th, "_rd_request", return_value=info):
        assert th._rd_get_info("tid", token="t") == info


def test_rd_unrestrict_returns_download_url(th):
    with patch.object(th, "_rd_request", return_value={"download": "https://d.real-debrid.com/x"}) as m:
        result = th._rd_unrestrict("https://rd-link", token="t")
    assert result == "https://d.real-debrid.com/x"
    assert m.call_args.args == ("POST", "/unrestrict/link")
    assert m.call_args.kwargs["data"] == {"link": "https://rd-link"}


# --- File picker prompt --------------------------------------------------

def _fake_rd_files():
    # Mirrors torrents/info: each file has id (NOT necessarily 1..N), path, bytes
    return [
        {"id": 10, "path": "/s01e01.mkv",  "bytes": int(2.1 * 1024**3)},
        {"id": 11, "path": "/s01e02.mkv",  "bytes": int(2.3 * 1024**3)},
        {"id": 12, "path": "/s01e03.mkv",  "bytes": int(2.0 * 1024**3)},
        {"id": 13, "path": "/rarbg.txt",   "bytes": 28 * 1024},
    ]


def test_prompt_file_selection_all(th, capsys):
    with patch("builtins.input", return_value=""):
        result = th._rd_prompt_file_selection(_fake_rd_files(), torrent_name="The.Wire.S01")
    assert result == "10,11,12,13"
    out = capsys.readouterr().out
    assert "4 files" in out
    assert "The.Wire.S01" in out
    assert "s01e02.mkv" in out
    assert "2.3 GB" in out
    assert "28.0 KB" in out


def test_prompt_file_selection_specific(th):
    with patch("builtins.input", return_value="1,3"):
        result = th._rd_prompt_file_selection(_fake_rd_files(), torrent_name="x")
    assert result == "10,12"  # maps display positions 1,3 → RD ids 10,12


def test_prompt_file_selection_range(th):
    with patch("builtins.input", return_value="1-3"):
        result = th._rd_prompt_file_selection(_fake_rd_files(), torrent_name="x")
    assert result == "10,11,12"


def test_prompt_file_selection_cancel(th):
    with patch("builtins.input", return_value="c"):
        result = th._rd_prompt_file_selection(_fake_rd_files(), torrent_name="x")
    assert result == "cancel"


def test_prompt_file_selection_reprompts_on_invalid(th, capsys):
    # First input invalid, second valid
    with patch("builtins.input", side_effect=["bogus", "1"]):
        result = th._rd_prompt_file_selection(_fake_rd_files(), torrent_name="x")
    assert result == "10"
    out = capsys.readouterr().out
    assert "Invalid selection" in out


def test_prompt_file_selection_strips_ansi_from_torrent_name(th, capsys):
    # Malicious uploader injects ANSI clear-screen + fake content into torrent name
    hostile_name = "legit.movie\x1b[2J\x1b[Hfake content"
    with patch("builtins.input", return_value="c"):
        th._rd_prompt_file_selection(_fake_rd_files(), torrent_name=hostile_name)
    out = capsys.readouterr().out
    assert "\x1b" not in out
    assert "legit.moviefake content" in out  # text preserved, escapes stripped


def test_prompt_file_selection_strips_ansi_from_filenames(th, capsys):
    hostile_files = [
        {"id": 1, "path": "/normal.mkv", "bytes": 1024},
        {"id": 2, "path": "/evil\x1b[Arewritten.mkv", "bytes": 1024},
    ]
    with patch("builtins.input", return_value="c"):
        th._rd_prompt_file_selection(hostile_files, torrent_name="t")
    out = capsys.readouterr().out
    assert "\x1b" not in out


@pytest.mark.parametrize("raw,expected", [
    ("plain", "plain"),
    ("with\x1b[31m color\x1b[0m reset", "with color reset"),
    ("clear\x1b[2Jscreen", "clearscreen"),
    ("cursor\x1b[F up", "cursor up"),
    ("title\x1b]0;spoof\x07after", "titleafter"),   # OSC with BEL terminator
    ("title\x1b]0;spoof\x1b\\after", "titleafter"), # OSC with ST terminator
    ("bare\x07bell", "barebell"),                   # BEL (C0 control)
    ("newline\nkept", "newline\nkept"),              # \n preserved
    ("tab\tkept", "tab\tkept"),                      # \t preserved
])
def test_strip_ansi(th, raw, expected):
    assert th._strip_ansi(raw) == expected


def test_strip_ansi_has_no_escape_chars_in_output(th):
    # Fuzz-style: whatever garbage is thrown in, the output must not contain ESC or C0 controls
    hostile = "a\x1b[Xb\x1b]payload\x07c\x1bM\x00d\x7fe"
    out = th._strip_ansi(hostile)
    assert "\x1b" not in out
    assert "\x00" not in out
    assert "\x7f" not in out


# --- Action dispatch -----------------------------------------------------

def test_apply_action_clipboard_single(th, capsys):
    with patch.object(th.pyperclip, "copy") as m_copy:
        th._rd_apply_action(["https://d.rd/x"], "clipboard")
    m_copy.assert_called_once_with("https://d.rd/x")
    assert "copied to clipboard" in capsys.readouterr().out


def test_apply_action_clipboard_multiple(th, capsys):
    with patch.object(th.pyperclip, "copy") as m_copy:
        th._rd_apply_action(["https://a", "https://b", "https://c"], "clipboard")
    m_copy.assert_called_once_with("https://a\nhttps://b\nhttps://c")
    out = capsys.readouterr().out
    assert "3 direct links" in out


def test_apply_action_print(th, capsys):
    th._rd_apply_action(["https://a", "https://b"], "print")
    out = capsys.readouterr().out
    assert "https://a\nhttps://b" in out


def test_apply_action_browser(th):
    with patch.object(th.webbrowser, "open") as m_open, patch.object(th.time, "sleep"):
        th._rd_apply_action(["https://u1", "https://u2"], "browser")
    assert m_open.call_args_list == [(("https://u1",),), (("https://u2",),)]


def test_apply_action_downie_url_encodes(th):
    with patch.object(th.webbrowser, "open") as m_open, patch.object(th.time, "sleep"):
        th._rd_apply_action(["https://d.rd/file with spaces.mkv"], "downie")
    called_url = m_open.call_args.args[0]
    assert called_url.startswith("downie://XUL/?url=")
    assert "file%20with%20spaces.mkv" in called_url


def test_apply_action_downie_multiple_sleeps_between(th):
    with patch.object(th.webbrowser, "open"), patch.object(th.time, "sleep") as m_sleep:
        th._rd_apply_action(["https://a", "https://b", "https://c"], "downie")
    # Sleeps between links, not after the last
    assert m_sleep.call_count == 2


@pytest.mark.parametrize("bad_scheme", [
    "file:///etc/passwd",
    "javascript:alert(1)",
    "tel:+15551234567",
    "shortcuts://run?x=y",
    "http://insecure.example/file",  # http is not allowed — only https
    "no-scheme-at-all",
    "",
])
def test_apply_action_rejects_non_https_schemes(th, capsys, bad_scheme):
    with patch.object(th.pyperclip, "copy") as m_copy, \
         patch.object(th.webbrowser, "open") as m_open:
        th._rd_apply_action([bad_scheme], "clipboard")
    m_copy.assert_not_called()
    m_open.assert_not_called()
    out = capsys.readouterr().out
    assert "unexpected scheme" in out or "No usable" in out


def test_apply_action_filters_mixed_bad_and_good(th, capsys):
    with patch.object(th.pyperclip, "copy") as m_copy:
        th._rd_apply_action(
            ["https://good.example/one", "file:///etc/passwd", "https://good.example/two"],
            "clipboard",
        )
    # Only the two https links make it through, joined
    m_copy.assert_called_once_with("https://good.example/one\nhttps://good.example/two")
    out = capsys.readouterr().out
    assert "unexpected scheme 'file'" in out


# --- _cmd_rd orchestrator ------------------------------------------------

def _entry(magnet="magnet:?xt=urn:btih:" + "01" * 20, link="https://tpb/x"):
    return {
        "name": "test.torrent",
        "link": link,
        "magnet": magnet,
        "seeders": 10, "leechers": 1, "size": "1 GiB", "ratio": "10.0",
    }


def _fake_info(files=None, links=None, status="downloaded"):
    files = files if files is not None else [{"id": 1, "path": "/x.mkv", "bytes": 1024}]
    links = links if links is not None else ["https://rd/link-1"]
    return {"status": status, "files": files, "links": links}


def test_cmd_rd_no_token_prints_help(th, capsys, monkeypatch):
    monkeypatch.delenv("RD_TOKEN", raising=False)
    with patch.object(th, "_load_config", return_value={}):
        th._cmd_rd(_entry())
    out = capsys.readouterr().out
    assert "token not configured" in out
    assert "RD_TOKEN" in out
    assert "real-debrid.com/apitoken" in out


def test_cmd_rd_cached_single_file_clipboard(th, capsys, monkeypatch):
    # Models the real RD lifecycle: peek response (files present, no links yet)
    # followed by post-select response (files + links). Previously both calls
    # returned the same object, which hid the two-phase structure.
    monkeypatch.setenv("RD_TOKEN", "tok")
    peek = _fake_info(files=[{"id": 1, "path": "/x.mkv", "bytes": 1024}], links=[])
    post = _fake_info(files=[{"id": 1, "path": "/x.mkv", "bytes": 1024}],
                     links=["https://rd/link-1"])
    with patch.object(th, "_load_config", return_value={}), \
         patch.object(th, "_rd_check_cached", return_value=True), \
         patch.object(th, "_rd_add_magnet", return_value="tid"), \
         patch.object(th, "_rd_select_files") as m_select, \
         patch.object(th, "_rd_get_info", side_effect=[peek, post]), \
         patch.object(th, "_rd_unrestrict", return_value="https://d.rd/x"), \
         patch.object(th.pyperclip, "copy") as m_copy:
        th._cmd_rd(_entry())
    m_select.assert_called_once_with("tid", "all", token="tok")
    m_copy.assert_called_once_with("https://d.rd/x")
    assert "Cached on Real-Debrid" in capsys.readouterr().out


def test_cmd_rd_cached_multi_file_prompts(th, monkeypatch):
    monkeypatch.setenv("RD_TOKEN", "tok")
    info = _fake_info(
        files=[
            {"id": 10, "path": "/a.mkv", "bytes": 1024**3},
            {"id": 11, "path": "/b.mkv", "bytes": 1024**3},
        ],
        links=["https://rd/1", "https://rd/2"],
    )
    with patch.object(th, "_load_config", return_value={}), \
         patch.object(th, "_rd_check_cached", return_value=True), \
         patch.object(th, "_rd_add_magnet", return_value="tid"), \
         patch.object(th, "_rd_select_files") as m_select, \
         patch.object(th, "_rd_get_info", return_value=info), \
         patch.object(th, "_rd_unrestrict", side_effect=["https://d1", "https://d2"]), \
         patch("builtins.input", return_value="1,2"), \
         patch.object(th.pyperclip, "copy"):
        th._cmd_rd(_entry())
    m_select.assert_called_once_with("tid", "10,11", token="tok")


def test_cmd_rd_cached_multi_file_cancel(th, capsys, monkeypatch):
    monkeypatch.setenv("RD_TOKEN", "tok")
    info = _fake_info(
        files=[{"id": 10, "path": "/a.mkv", "bytes": 1}, {"id": 11, "path": "/b.mkv", "bytes": 1}],
    )
    with patch.object(th, "_load_config", return_value={}), \
         patch.object(th, "_rd_check_cached", return_value=True), \
         patch.object(th, "_rd_add_magnet", return_value="tid"), \
         patch.object(th, "_rd_select_files") as m_select, \
         patch.object(th, "_rd_get_info", return_value=info), \
         patch("builtins.input", return_value="c"):
        th._cmd_rd(_entry())
    m_select.assert_not_called()
    assert "Cancelled" in capsys.readouterr().out


def test_cmd_rd_uncached_yes(th, capsys, monkeypatch):
    monkeypatch.setenv("RD_TOKEN", "tok")
    with patch.object(th, "_load_config", return_value={}), \
         patch.object(th, "_rd_check_cached", return_value=False), \
         patch.object(th, "_rd_add_magnet", return_value="tid"), \
         patch.object(th, "_rd_select_files") as m_select, \
         patch("builtins.input", return_value="y"), \
         patch.object(th.webbrowser, "open") as m_open:
        th._cmd_rd(_entry())
    m_select.assert_called_once_with("tid", "all", token="tok")
    m_open.assert_called_once_with("https://real-debrid.com/torrents")
    assert "Submitted" in capsys.readouterr().out


def test_cmd_rd_uncached_no(th, monkeypatch):
    monkeypatch.setenv("RD_TOKEN", "tok")
    with patch.object(th, "_load_config", return_value={}), \
         patch.object(th, "_rd_check_cached", return_value=False), \
         patch.object(th, "_rd_add_magnet") as m_add, \
         patch("builtins.input", return_value="n"):
        th._cmd_rd(_entry())
    m_add.assert_not_called()


def test_cmd_rd_bad_hash(th, capsys, monkeypatch):
    monkeypatch.setenv("RD_TOKEN", "tok")
    with patch.object(th, "_load_config", return_value={}):
        th._cmd_rd(_entry(magnet="magnet:?dn=no-hash"))
    assert "parse info-hash" in capsys.readouterr().out


def test_cmd_rd_torrent_error_status(th, capsys, monkeypatch):
    monkeypatch.setenv("RD_TOKEN", "tok")
    info_err = _fake_info(status="magnet_error")
    with patch.object(th, "_load_config", return_value={}), \
         patch.object(th, "_rd_check_cached", return_value=True), \
         patch.object(th, "_rd_add_magnet", return_value="tid"), \
         patch.object(th, "_rd_select_files"), \
         patch.object(th, "_rd_get_info", return_value=info_err):
        th._cmd_rd(_entry())
    out = capsys.readouterr().out
    assert "magnet_error" in out


def test_cmd_rd_cached_but_links_not_ready(th, capsys, monkeypatch):
    # Edge case: status is non-terminal and links are empty (brief RD lag).
    # The first info call returns files; the second (post-select) still shows no links.
    monkeypatch.setenv("RD_TOKEN", "tok")
    info_peek = _fake_info(files=[{"id": 1, "path": "/x.mkv", "bytes": 1024}], links=[])
    info_post = {"status": "magnet_conversion", "files": info_peek["files"], "links": []}
    with patch.object(th, "_load_config", return_value={}), \
         patch.object(th, "_rd_check_cached", return_value=True), \
         patch.object(th, "_rd_add_magnet", return_value="tid"), \
         patch.object(th, "_rd_select_files"), \
         patch.object(th, "_rd_get_info", side_effect=[info_peek, info_post]), \
         patch.object(th, "_rd_unrestrict") as m_unrestrict:
        th._cmd_rd(_entry())
    m_unrestrict.assert_not_called()
    out = capsys.readouterr().out
    assert "hasn't finished processing" in out
    assert "magnet_conversion" in out


def test_cmd_rd_rd_error_printed_not_raised(th, capsys, monkeypatch):
    monkeypatch.setenv("RD_TOKEN", "tok")
    with patch.object(th, "_load_config", return_value={}), \
         patch.object(th, "_rd_check_cached", side_effect=th._RdError("my msg")):
        th._cmd_rd(_entry())  # must not raise
    assert "my msg" in capsys.readouterr().out


def test_cmd_rd_keyerror_in_addmagnet_does_not_crash(th, capsys, monkeypatch):
    # If RD returns 201 but the JSON body lacks the 'id' key, _rd_add_magnet raises
    # KeyError. _cmd_rd must catch it and print a friendly message instead of crashing.
    monkeypatch.setenv("RD_TOKEN", "tok")
    with patch.object(th, "_load_config", return_value={}), \
         patch.object(th, "_rd_check_cached", return_value=True), \
         patch.object(th, "_rd_add_magnet", side_effect=KeyError("id")):
        th._cmd_rd(_entry())  # must not raise
    out = capsys.readouterr().out
    assert "Unexpected Real-Debrid response" in out
    assert "KeyError" in out


def test_cmd_rd_typeerror_in_unrestrict_does_not_crash(th, capsys, monkeypatch):
    monkeypatch.setenv("RD_TOKEN", "tok")
    with patch.object(th, "_load_config", return_value={}), \
         patch.object(th, "_rd_check_cached", return_value=True), \
         patch.object(th, "_rd_add_magnet", return_value="tid"), \
         patch.object(th, "_rd_select_files"), \
         patch.object(th, "_rd_get_info", return_value=_fake_info()), \
         patch.object(th, "_rd_unrestrict", side_effect=TypeError("None is not subscriptable")):
        th._cmd_rd(_entry())  # must not raise
    out = capsys.readouterr().out
    assert "Unexpected Real-Debrid response" in out
