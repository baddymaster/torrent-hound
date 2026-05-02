"""Real-Debrid API client.

Covers: hash extraction from magnet, the HTTP layer (`_rd_request`) with
rate-limit retry and CDN-block detection, the high-level torrent flow
helpers (addMagnet → selectFiles → unrestrict), ANSI-escape stripping
for untrusted torrent metadata, and the action dispatch (`_rd_dispatch`)
that the TUI's RD worker calls after unrestricting.

The orchestrator lives in `torrent_hound.tui._rd_worker`; this module
provides the helpers it composes.
"""

import base64
import re
import socket
import time
import urllib.parse
import webbrowser

import pyperclip
import requests

_RD_HASH_RE = re.compile(r"xt=urn:btih:([0-9a-fA-F]{40}|[A-Za-z2-7]{32})")


def _rd_parse_hash(magnet):
    if not magnet:
        return None
    match = _RD_HASH_RE.search(magnet)
    if not match:
        return None
    raw = match.group(1)
    if len(raw) == 40:
        return raw.lower()
    # 32-char base32 → decode to 20 bytes → hex-encode to 40 chars
    return base64.b32decode(raw.upper()).hex()


def _human_size(n):
    if n < 1024:
        return f"{n} B"
    for unit in ("KB", "MB", "GB", "TB"):
        n /= 1024
        if n < 1024:
            return f"{n:.1f} {unit}"
    return f"{n:.1f} PB"


_RD_API = "https://api.real-debrid.com/rest/1.0"


class _RdError(Exception):
    """Carries a pre-formatted user-facing message; caller just prints it.

    The optional `error_code` attribute mirrors RD's documented numeric error_code
    from the response body when one was available. Callers can use it to suppress
    or branch on specific failure modes (e.g., `_rd_check_cached` swallows
    error_code 37 'endpoint disabled' to degrade gracefully when RD turns off the
    undocumented instantAvailability endpoint for an account).
    """
    def __init__(self, message, error_code=None):
        super().__init__(message)
        self.error_code = error_code


def _rd_has_cdn_markers(headers):
    if "cf-ray" in headers or "cf-mitigated" in headers:
        return True
    server = headers.get("server", "")
    return server.lower().startswith("cloudflare")


# Documented RD numeric error_codes (see https://api.real-debrid.com/). RD always
# returns these in the response body alongside any non-2xx status. Mapping to a
# user-facing message lets us distinguish "your account is locked" from "your IP
# isn't whitelisted" — both 403s but completely different remediations.
_RD_ERROR_MESSAGES = {
    8:  "Real-Debrid rejected the token. Run `torrent-hound --configure-rd` to enter a fresh one, or set the RD_TOKEN env var.",
    9:  "Real-Debrid denied the operation. Your account may be free-tier, locked, or this endpoint is restricted for your token.",
    14: "Your Real-Debrid account is locked. Contact RD support.",
    20: "Real-Debrid's chosen hoster is premium-only for your account. Upgrade or try a different torrent.",
    21: "Real-Debrid says you have too many active torrents. Wait for some to finish or delete them at https://real-debrid.com/torrents.",
    22: "Your current IP address isn't whitelisted on your RD account. Manage IP restrictions at https://real-debrid.com/account.",
    23: "Real-Debrid fair-use quota exhausted. Quota resets daily; see https://real-debrid.com/user.",
    34: "Real-Debrid rate limit hit (250 req/min). Wait a minute and retry.",
    37: "This Real-Debrid endpoint is disabled for your account. Contact RD support.",
}


def _rd_parse_error_body(resp):
    """Best-effort extract (error_code, error_message) from a RD error response.

    Returns (None, None) when the body is missing, non-JSON, or not a dict.
    """
    try:
        body = resp.json()
    except ValueError:
        return (None, None)
    if not isinstance(body, dict):
        return (None, None)
    return (body.get("error_code"), body.get("error"))


def _rd_request(method, path, token, data=None):
    """Call RD. Returns parsed JSON dict, or None for 202/204. Raises _RdError.

    On HTTP 429 (rate limit) the call waits 60 seconds and retries ONCE before
    surfacing the error. RD docs warn that "all refused requests will return
    HTTP 429 error and will count in the limit (bruteforcing will leave you
    blocked for undefined amount of time)" — so no exponential backoff, no
    multi-retry. One free retry, then bail.
    """
    url = _RD_API + path
    headers = {"Authorization": f"Bearer {token}"}

    for attempt in (1, 2):
        try:
            resp = requests.request(method, url, headers=headers, data=data, timeout=3)
        except requests.Timeout:
            raise _RdError("Real-Debrid timed out. Try again in a moment.") from None
        except requests.ConnectionError as e:
            cause = e.__cause__
            while cause is not None:
                if isinstance(cause, socket.gaierror):
                    raise _RdError(
                        "DNS lookup for api.real-debrid.com failed. Your ISP/DNS "
                        "may be blocking it — try a VPN or DoH (1.1.1.1, 8.8.8.8)."
                    ) from None
                cause = getattr(cause, "__cause__", None)
            raise _RdError(
                "Couldn't reach real-debrid.com. Check your connection or try "
                "a VPN if your ISP blocks it."
            ) from None

        if resp.status_code != 429 or attempt == 2:
            break
        print("Real-Debrid rate limit hit; waiting 60s and retrying once...")
        time.sleep(60)

    s = resp.status_code
    if s in (202, 204):
        # 204: success, no body (selectFiles first call, delete, settings update).
        # 202: 'Action already done' per RD docs — selectFiles called twice on same
        # torrent. Body is empty; treat as idempotent success.
        return None
    if 200 <= s < 300:
        # Per RD docs (https://api.real-debrid.com/): 200 for GETs and POST /unrestrict/link,
        # 201 for POST /torrents/addMagnet and PUT /torrents/addTorrent. All carry JSON.
        try:
            return resp.json()
        except ValueError:
            # 200 OK but body isn't JSON — typically a captive portal or transparent
            # proxy intercepting the request. Don't leak the raw HTML.
            raise _RdError(
                "Real-Debrid returned a non-JSON response. Likely a captive portal "
                "or proxy; check your connection."
            ) from None
    # CDN/proxy 403 first — body is HTML not JSON, so error_code parsing won't help
    if s == 403 and _rd_has_cdn_markers(resp.headers):
        raise _RdError(
            "Real-Debrid reachable but returning a block page — likely CDN "
            "or ISP intermediary. Try a VPN."
        )

    # Prefer specific message keyed off RD's documented error_code in the body
    err_code, err_msg = _rd_parse_error_body(resp)
    if err_code in _RD_ERROR_MESSAGES:
        raise _RdError(_RD_ERROR_MESSAGES[err_code], error_code=err_code)

    # Status-code fallbacks for cases where body is missing or has an unmapped code
    if s == 401:
        raise _RdError(
            "Real-Debrid rejected the token. Run `torrent-hound --configure-rd` to "
            "enter a fresh one, or set the RD_TOKEN env var."
        )
    if s == 451:
        raise _RdError("Real-Debrid is geo-blocked on this connection (HTTP 451). Try a VPN.")
    if s == 403:
        raise _RdError("Real-Debrid refused the request (403). Likely account/quota issue.")
    if s == 429:
        raise _RdError("Real-Debrid rate limit hit. Wait a minute and retry.")
    if s == 404:
        raise _RdError(
            "Real-Debrid doesn't have that resource (404). The torrent id may have "
            "expired — run the rd command again to get a fresh one."
        )
    if s == 400:
        # 400 usually means a malformed parameter we sent; include body context if RD gave us one
        ctx = f": {err_msg}" if err_msg else ""
        raise _RdError(f"Real-Debrid rejected the request as malformed (400){ctx}.")

    # Generic — surface body context if RD gave us anything to work with
    if err_code is not None or err_msg:
        raise _RdError(
            f"Real-Debrid error {s} (error_code={err_code}): {err_msg or 'no message'}.",
            error_code=err_code,
        )
    raise _RdError(f"Real-Debrid error {s}. Try again.")


def _rd_add_magnet(magnet, token):
    data = _rd_request("POST", "/torrents/addMagnet", token=token, data={"magnet": magnet})
    return data["id"]


def _rd_select_files(torrent_id, files, token):
    _rd_request("POST", f"/torrents/selectFiles/{torrent_id}", token=token, data={"files": files})


def _rd_get_info(torrent_id, token):
    return _rd_request("GET", f"/torrents/info/{torrent_id}", token=token)


def _rd_unrestrict(link, token):
    data = _rd_request("POST", "/unrestrict/link", token=token, data={"link": link})
    return data["download"]


_ANSI_ESCAPE_RE = re.compile(
    r'\x1b\][\s\S]*?(?:\x07|\x1b\\)'      # OSC ... (BEL or ST terminator)
    r'|\x1b\[[0-?]*[ -/]*[@-~]'           # CSI ... final-byte
    r'|\x1b[@-_]'                          # ESC + single final byte (SS2, SS3, etc.)
    r'|\x1b'                               # Stray / unterminated ESC
    r'|[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]'   # C0 controls + DEL (keep \t \n \r)
)


def _strip_ansi(s):
    """Remove ANSI escape sequences and C0 control characters.

    Torrent names and filenames come from untrusted sources. A malicious uploader
    could inject escape sequences that clear the terminal, overwrite the file
    picker with spoofed rows, or rewrite the [y/N] confirmation prompt. Strip
    them before printing anything externally sourced.
    """
    return _ANSI_ESCAPE_RE.sub('', s)


def _rd_dispatch(links, action):
    """URL-scheme-validated dispatch of RD direct links via the configured action.

    Defends against hostile / MITM'd RD responses sneaking `file://`,
    `javascript:`, etc. links through by allowlisting `https://` only.
    Per-action behaviour: clipboard / print / browser / Downie. Never
    prints — the TUI surfaces outcome via toasts. Returns a single
    user-facing summary string. Raises `_RdError` if no usable links
    remain after filtering.
    """
    safe = [link for link in links if urllib.parse.urlparse(link).scheme == "https"]
    skipped = len(links) - len(safe)
    if not safe:
        raise _RdError("No usable Real-Debrid direct links (all had unexpected URL schemes).")

    n = len(safe)
    suffix = f" ({skipped} skipped — bad URL scheme)" if skipped else ""

    if action == "clipboard":
        pyperclip.copy(safe[0] if n == 1 else "\n".join(safe))
        msg = "1 link copied to clipboard" if n == 1 else f"{n} links copied to clipboard"
        return f"Real-Debrid: {msg}{suffix}"
    if action == "print":
        # In TUI we can't really "print" — mirror to clipboard so the user
        # gets the same effect (links available outside the TUI). The toast
        # tells them where to find them.
        pyperclip.copy("\n".join(safe))
        return f"Real-Debrid: {n} link(s) copied to clipboard (print action){suffix}"
    for i, link in enumerate(safe):
        if action == "browser":
            webbrowser.open(link)
        elif action == "downie":
            webbrowser.open("downie://XUL/?url=" + urllib.parse.quote(link, safe=""))
        if i < n - 1:
            time.sleep(0.2)
    return f"Real-Debrid: {n} link(s) sent via {action}{suffix}"
