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


def test_rd_request_429_persistent_raises_after_one_retry(th):
    # Both attempts return 429 → one sleep, then raise
    with patch.object(th.requests, "request", return_value=_mk_response(429)), \
         patch.object(th.time, "sleep") as m_sleep:
        with pytest.raises(th._RdError) as exc:
            th._rd_request("GET", "/x", token="t")
    assert "rate limit" in str(exc.value)
    m_sleep.assert_called_once_with(60)


def test_rd_request_429_then_success_returns_json(th):
    # First attempt rate-limited, second attempt succeeds — return the JSON
    rate_limited = _mk_response(429)
    success = _mk_response(200, json_body={"id": "x"})
    with patch.object(th.requests, "request", side_effect=[rate_limited, success]) as m_req, \
         patch.object(th.time, "sleep") as m_sleep:
        body = th._rd_request("GET", "/x", token="t")
    assert body == {"id": "x"}
    assert m_req.call_count == 2
    m_sleep.assert_called_once_with(60)


def test_rd_request_non_429_does_not_retry(th):
    # 503 should NOT trigger retry (only 429 does)
    with patch.object(th.requests, "request", return_value=_mk_response(503)) as m_req, \
         patch.object(th.time, "sleep") as m_sleep:
        with pytest.raises(th._RdError):
            th._rd_request("GET", "/x", token="t")
    assert m_req.call_count == 1
    m_sleep.assert_not_called()


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


# --- error_code mapping (per RD docs) ------------------------------------

@pytest.mark.parametrize("err_code,expected_substring", [
    (8,  "rejected the token"),
    (9,  "denied the operation"),
    (14, "account is locked"),
    (20, "premium-only"),
    (21, "too many active torrents"),
    (22, "IP address isn't whitelisted"),
    (23, "fair-use quota exhausted"),
    (34, "rate limit"),
    (37, "endpoint is disabled"),
])
def test_rd_request_known_error_code_uses_specific_message(th, err_code, expected_substring):
    # 403 is a typical wrapper for these — the mapping should win regardless of status
    resp = _mk_response(403, json_body={"error": "rd msg", "error_code": err_code})
    with patch.object(th.requests, "request", return_value=resp):
        with pytest.raises(th._RdError) as exc:
            th._rd_request("GET", "/x", token="t")
    assert expected_substring in str(exc.value)


def test_rd_request_unknown_error_code_falls_through_with_body_context(th):
    # 99 isn't in our mapping, and 502 has no specific status fallback — falls to generic
    resp = _mk_response(502, json_body={"error": "bad thing", "error_code": 99})
    with patch.object(th.requests, "request", return_value=resp):
        with pytest.raises(th._RdError) as exc:
            th._rd_request("GET", "/x", token="t")
    msg = str(exc.value)
    assert "502" in msg
    assert "error_code=99" in msg
    assert "bad thing" in msg


def test_rd_request_400_specific_message_with_body_context(th):
    resp = _mk_response(400, json_body={"error": "Required parameter missing", "error_code": 1})
    with patch.object(th.requests, "request", return_value=resp):
        with pytest.raises(th._RdError) as exc:
            th._rd_request("POST", "/torrents/addMagnet", token="t")
    msg = str(exc.value)
    assert "400" in msg
    assert "malformed" in msg
    assert "Required parameter missing" in msg


def test_rd_request_400_no_body(th):
    resp = _mk_response(400)  # empty body
    with patch.object(th.requests, "request", return_value=resp):
        with pytest.raises(th._RdError) as exc:
            th._rd_request("POST", "/x", token="t")
    assert "malformed" in str(exc.value)


def test_rd_request_404_specific_message(th):
    resp = _mk_response(404, json_body={"error": "Resource not found", "error_code": 7})
    with patch.object(th.requests, "request", return_value=resp):
        with pytest.raises(th._RdError) as exc:
            th._rd_request("GET", "/torrents/info/stale-id", token="t")
    msg = str(exc.value)
    assert "404" in msg
    assert "torrent id" in msg.lower()
    assert "expired" in msg.lower()


def test_rd_request_error_code_preempts_status_fallback(th):
    # Status 401 normally → "rejected the token", but error_code=14 means account locked.
    # The body's specific code wins.
    resp = _mk_response(401, json_body={"error": "locked", "error_code": 14})
    with patch.object(th.requests, "request", return_value=resp):
        with pytest.raises(th._RdError) as exc:
            th._rd_request("GET", "/x", token="t")
    assert "account is locked" in str(exc.value)
    assert "rejected the token" not in str(exc.value)


def test_rd_request_cdn_403_preempts_error_code(th):
    # If response has Cloudflare markers, the body is HTML junk — error_code parsing
    # would fail/lie. CDN check must run before body parsing.
    resp = _mk_response(403, headers={"cf-ray": "abc"}, json_body={"error_code": 22})
    with patch.object(th.requests, "request", return_value=resp):
        with pytest.raises(th._RdError) as exc:
            th._rd_request("GET", "/x", token="t")
    assert "block page" in str(exc.value)
    assert "IP address" not in str(exc.value)  # not the error_code-22 message


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


def test_rd_request_202_action_already_done(th):
    # selectFiles called a second time returns 202 with no body — idempotent success per RD docs.
    # Without explicit handling this would fall into the 2xx range, attempt resp.json(),
    # raise ValueError, and surface as a misleading "non-JSON / captive portal" error.
    resp = _mk_response(202)
    resp.json.side_effect = ValueError("No JSON")
    with patch.object(th.requests, "request", return_value=resp):
        assert th._rd_request("POST", "/torrents/selectFiles/x", token="t") is None


def test_rd_request_200_non_json_raises_rd_error(th):
    # Captive portal / transparent proxy returning HTML with HTTP 200
    resp = _mk_response(200)
    resp.json.side_effect = ValueError("Expecting value")
    with patch.object(th.requests, "request", return_value=resp):
        with pytest.raises(th._RdError) as exc:
            th._rd_request("GET", "/x", token="t")
    assert "non-JSON" in str(exc.value) or "captive portal" in str(exc.value).lower()


# --- Endpoint wrappers ---------------------------------------------------


def test_rd_error_carries_error_code_attribute(th):
    # Verify the _RdError exception type carries error_code through correctly.
    e1 = th._RdError("msg only")
    assert e1.error_code is None
    e2 = th._RdError("msg with code", error_code=22)
    assert e2.error_code == 22
    assert str(e2) == "msg with code"


def test_rd_request_attaches_error_code_to_exception(th):
    # When the body has a known error_code, the raised _RdError must carry it.
    resp = _mk_response(403, json_body={"error_code": 22})
    with patch.object(th.requests, "request", return_value=resp):
        with pytest.raises(th._RdError) as exc:
            th._rd_request("GET", "/x", token="t")
    assert exc.value.error_code == 22


def test_rd_add_magnet_returns_id(th):
    with patch.object(th.realdebrid, "_rd_request", return_value={"id": "abc", "uri": "..."}) as m:
        result = th._rd_add_magnet("magnet:?xt=...", token="t")
    assert result == "abc"
    assert m.call_args.args == ("POST", "/torrents/addMagnet")
    assert m.call_args.kwargs["data"] == {"magnet": "magnet:?xt=..."}


def test_rd_select_files_all(th):
    with patch.object(th.realdebrid, "_rd_request", return_value=None) as m:
        th._rd_select_files("tid", "all", token="t")
    assert m.call_args.args == ("POST", "/torrents/selectFiles/tid")
    assert m.call_args.kwargs["data"] == {"files": "all"}


def test_rd_select_files_specific_ids(th):
    with patch.object(th.realdebrid, "_rd_request", return_value=None) as m:
        th._rd_select_files("tid", "1,3,5", token="t")
    assert m.call_args.kwargs["data"] == {"files": "1,3,5"}


def test_rd_get_info(th):
    info = {"status": "downloaded", "files": [], "links": ["l1", "l2"]}
    with patch.object(th.realdebrid, "_rd_request", return_value=info):
        assert th._rd_get_info("tid", token="t") == info


def test_rd_unrestrict_returns_download_url(th):
    with patch.object(th.realdebrid, "_rd_request", return_value={"download": "https://d.real-debrid.com/x"}) as m:
        result = th._rd_unrestrict("https://rd-link", token="t")
    assert result == "https://d.real-debrid.com/x"
    assert m.call_args.args == ("POST", "/unrestrict/link")
    assert m.call_args.kwargs["data"] == {"link": "https://rd-link"}


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

def test_dispatch_clipboard_single_returns_message(th):
    with patch.object(th.pyperclip, "copy") as m_copy:
        result = th._rd_dispatch(["https://d.rd/x"], "clipboard")
    m_copy.assert_called_once_with("https://d.rd/x")
    assert "Real-Debrid" in result and "1 link" in result


def test_dispatch_clipboard_multiple_returns_message(th):
    with patch.object(th.pyperclip, "copy") as m_copy:
        result = th._rd_dispatch(["https://a", "https://b", "https://c"], "clipboard")
    m_copy.assert_called_once_with("https://a\nhttps://b\nhttps://c")
    assert "3 links" in result


def test_dispatch_print_writes_to_clipboard_in_tui_context(th):
    """`print` action in the TUI has no terminal to print to; mirror to clipboard
    so the user can still get the links out, and signal the substitution in the
    return message."""
    with patch.object(th.pyperclip, "copy") as m_copy:
        result = th._rd_dispatch(["https://a", "https://b"], "print")
    m_copy.assert_called_once_with("https://a\nhttps://b")
    assert "clipboard" in result and "print action" in result


def test_dispatch_browser_opens_each(th):
    with patch.object(th.webbrowser, "open") as m_open, patch.object(th.time, "sleep"):
        result = th._rd_dispatch(["https://u1", "https://u2"], "browser")
    assert m_open.call_args_list == [(("https://u1",),), (("https://u2",),)]
    assert "browser" in result and "2 link" in result


def test_dispatch_downie_url_encodes(th):
    with patch.object(th.webbrowser, "open") as m_open, patch.object(th.time, "sleep"):
        th._rd_dispatch(["https://d.rd/file with spaces.mkv"], "downie")
    called_url = m_open.call_args.args[0]
    assert called_url.startswith("downie://XUL/?url=")
    assert "file%20with%20spaces.mkv" in called_url


@pytest.mark.parametrize("bad_scheme", [
    "file:///etc/passwd",
    "javascript:alert(1)",
    "tel:+15551234567",
    "http://insecure.example/file",
])
def test_dispatch_raises_when_no_usable_links(th, bad_scheme):
    """All-filtered case must raise (caller surfaces the message as a toast),
    not silently succeed with zero links."""
    with patch.object(th.pyperclip, "copy") as m_copy, \
         patch.object(th.webbrowser, "open") as m_open:
        with pytest.raises(th._RdError, match="No usable"):
            th._rd_dispatch([bad_scheme], "clipboard")
    m_copy.assert_not_called()
    m_open.assert_not_called()


def test_dispatch_mentions_skipped_count_when_some_filtered(th):
    """Mixed good + bad → succeed with the good ones, but flag the skipped
    count in the message so the user knows the count doesn't match what RD
    initially returned."""
    with patch.object(th.pyperclip, "copy"):
        result = th._rd_dispatch(
            ["https://good", "file:///etc/passwd", "https://better"],
            "clipboard",
        )
    assert "skipped" in result
    assert "bad URL scheme" in result
