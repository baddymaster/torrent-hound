"""Terminal UI for torrent-hound's interactive mode.

Single-screen rich.live app. Replaces the old REPL `Enter command :` loop
with arrow-key navigation, mode-aware footer, live filtering, and inline
RD integration.

Architecture + screen model documented in
tasks/specs/2026-04-25-tui-implementation-spec.md. This file is being
filled in incrementally, one commit per step.
"""
from __future__ import annotations

import random
import re
import select
import sys
import termios
import threading
import time
import tty
import webbrowser
from contextlib import contextmanager
from dataclasses import dataclass, field

import pyperclip
from rich.console import Group
from rich.layout import Layout
from rich.live import Live
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

from torrent_hound import state as _state
from torrent_hound.realdebrid import _cmd_rd
from torrent_hound.sources import searchAllSites
from torrent_hound.ui import console as _console

# ── modes ──────────────────────────────────────────────────────────────
LOADING = "loading"
RESULTS = "results"
FILTER = "filter"
RD_PICKER = "rd_picker"
RD_WAITING = "rd_waiting"
HELP = "help"


# N3 — palette. One place to tune the entire look. Inline color strings
# elsewhere should reference these rather than redefining them.
PALETTE = {
    "accent":   "bold #ffb84d",   # selected row, primary action
    "headline": "bold",           # headline / column headers
    "metadata": "dim",            # secondary info, separators
    "ok":       "green",          # success markers (toast, source ✓)
    "warn":     "yellow",         # cache hit, partial state
    "err":      "red",            # failed source, hard error
    "blink":    "bold #ffb84d blink",
}

# N1 — toasts. Auto-dismiss after this many seconds.
TOAST_TTL_SECONDS = 3.0


# Rotating-verb pool, search-phase only. Torrent-themed by design — every
# phrase maps to something a multi-source torrent search might be doing.
# RD-phase verbs land in step 8.
SEARCH_VERBS = [
    "Sniffing the trackers", "Catching a whiff of seeders", "Scenting magnets",
    "Picking up tracks", "Nosing the swarm", "Following the announce trail",
    "Combing the DHT", "Pawing through mirrors", "Canvassing seeders",
    "Scenting fresh torrents", "Nosing for peers", "Sniffing bencode",
    "Hunting seeders", "Stalking peers", "Prowling for trackers",
    "Chasing hashes", "Baying at trackers", "Treeing the torrent",
    "Hot on the scrape", "Cornering the swarm", "Running down leechers",
    "Closing on the infohash", "Dogging the announce",
    "Fetching magnets", "Hauling bitfields", "Dragging home the .torrent",
    "Bringing back the payload", "Scooping up seeders", "Wrangling peers",
    "Carting off chunks", "Lugging the swarm home", "Reeling in hashes",
    "Sieving peers", "Peeling packets", "Decoding magnets",
    "Unweaving trackers", "Stitching chunks", "Parsing the bitfield",
    "Shaking the DHT", "Rattling trackers", "Waking the swarm",
    "Herding peers", "Polling announces", "Unchoking peers",
    "Walking the DHT", "Hashing chunks", "Reticulating pieces",
    "Verifying infohash", "Handshaking", "Fanning out", "Merging swarms",
    "Scraping trackers", "Announcing to swarm", "Resolving peers",
    "Parsing bencode", "Tallying seeders", "Sieving leechers",
]
VERB_ROTATE_SECONDS = 2.0


@dataclass
class _AppState:
    """All TUI state in one place. Render is a pure function of this."""
    mode: str = LOADING
    selected_idx: int = 0
    filter_text: str = ""
    toast: str | None = None
    # Per-source progress: {source_name: status_string}.
    # Status: "fetching" | "cached" | "ok:N" | "empty".
    source_progress: dict = field(default_factory=dict)
    # Rotating verb shown during LOADING. Swap every ~VERB_ROTATE_SECONDS.
    current_verb: str = "Sniffing the trackers"
    verb_set_at: float = 0.0
    # Fetch timing for the run-summary line (M5).
    fetch_started_at: float = 0.0
    fetch_elapsed: float = 0.0
    # Set when the user requests RD on a row; main loop suspends Live and
    # runs _cmd_rd then clears this. None at rest.
    rd_request_entry: dict | None = None
    # Wall-clock when toast was set; loop expires after TOAST_TTL_SECONDS.
    toast_set_at: float = 0.0


def _set_toast(state: _AppState, message: str) -> None:
    state.toast = message
    state.toast_set_at = time.monotonic()


def _expire_toast(state: _AppState) -> None:
    if state.toast and (time.monotonic() - state.toast_set_at) >= TOAST_TTL_SECONDS:
        state.toast = None


# ── input ──────────────────────────────────────────────────────────────
@contextmanager
def cbreak():
    """Put stdin into cbreak mode so we can read single keys without Enter."""
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def read_key() -> str:
    """Read one keypress (or escape sequence) from stdin in cbreak mode."""
    ch = sys.stdin.read(1)
    if ch != "\x1b":
        return ch
    seq = sys.stdin.read(2)
    return {
        "[A": "UP", "[B": "DOWN", "[C": "RIGHT", "[D": "LEFT",
        "[H": "HOME", "[F": "END",
    }.get(seq, "ESC")


# ── action handlers ────────────────────────────────────────────────────
# Each returns the toast message to surface; rendering is the loop's job.
def _action_copy(entry) -> str:
    pyperclip.copy(str(entry["magnet"]))
    return "Magnet copied to clipboard"


def _action_open_page(entry) -> str:
    webbrowser.open(entry["link"], new=2)
    return "Opened torrent page in browser"


def _action_send_to_client(entry) -> str:
    webbrowser.open(entry["magnet"], new=2)
    return "Magnet sent to default torrent client"


def _action_seedr(entry) -> str:
    pyperclip.copy(str(entry["magnet"]))
    webbrowser.open("https://www.seedr.cc", new=2)
    return "Magnet copied + Seedr opened"


_RESULTS_ACTIONS = {
    "c": _action_copy,
    "\r": _action_copy,
    "\n": _action_copy,
    "o": _action_open_page,
    "d": _action_send_to_client,
    "s": _action_seedr,
}


# ── helpers ────────────────────────────────────────────────────────────
def _all_results() -> list[dict]:
    return _state.results or []


def _visible_results(state: _AppState) -> list[dict]:
    """Filter `_state.results` by `state.filter_text` (substring, case-insensitive)."""
    rows = _all_results()
    if not state.filter_text:
        return rows
    needle = state.filter_text.lower()
    return [r for r in rows if needle in r.get("name", "").lower()]


def _selected_entry(state: _AppState) -> dict | None:
    rows = _visible_results(state)
    if not rows:
        return None
    return rows[state.selected_idx]


def _handle_filter_key(state: _AppState, key: str) -> bool:
    """Filter-mode input: build state.filter_text; esc cancels, enter accepts."""
    if key == "ESC":
        state.filter_text = ""
        state.mode = RESULTS
        state.selected_idx = 0
    elif key in ("\r", "\n"):
        state.mode = RESULTS
        state.selected_idx = 0
    elif key == "\x7f":  # backspace
        state.filter_text = state.filter_text[:-1]
        state.selected_idx = 0
    elif len(key) == 1 and key.isprintable():
        state.filter_text += key
        state.selected_idx = 0
    return True


def handle_key(state: _AppState, key: str) -> bool:
    """Mutates state in-place. Returns False to break the event loop."""
    if state.mode == FILTER:
        return _handle_filter_key(state, key)

    if key == "q":
        return False

    if state.mode == RESULTS:
        rows = _visible_results(state)
        if key == "UP":
            state.selected_idx = max(0, state.selected_idx - 1)
        elif key == "DOWN":
            state.selected_idx = min(max(0, len(rows) - 1), state.selected_idx + 1)
        elif key == "/":
            state.mode = FILTER
            state.filter_text = ""
            state.selected_idx = 0
        elif key in _RESULTS_ACTIONS:
            entry = _selected_entry(state)
            if entry is not None:
                _set_toast(state, _RESULTS_ACTIONS[key](entry))
        elif key == "r":
            entry = _selected_entry(state)
            if entry is not None:
                # Main loop picks this up, suspends Live, runs _cmd_rd, restarts.
                state.rd_request_entry = entry

    return True


# ── render ─────────────────────────────────────────────────────────────
def _build_layout() -> Layout:
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=2),
        Layout(name="body"),
        Layout(name="toast", size=1),
        Layout(name="footer", size=1),
    )
    return layout


_PROGRESS_GLYPHS = {
    "fetching": ("⠋", PALETTE["accent"]),
    "cached":   ("⚡", PALETTE["warn"]),
    "empty":    ("·", PALETTE["metadata"]),
}


def _progress_glyph(status: str) -> tuple[str, str]:
    if status.startswith("ok:"):
        return ("✓", PALETTE["ok"])
    return _PROGRESS_GLYPHS.get(status, ("?", PALETTE["metadata"]))


def _render_progress_strip(state: _AppState) -> Text:
    """One-line summary: 'TPB ⠋  YTS ✓  EZTV ⚡' style."""
    if not state.source_progress:
        return Text("(starting fetch…)", style=PALETTE["metadata"])
    parts = []
    for name, status in state.source_progress.items():
        glyph, glyph_style = _progress_glyph(status)
        parts.append((f"{name} ", PALETTE["headline"]))
        parts.append((f"{glyph} ", glyph_style))
        if status.startswith("ok:"):
            count = status.split(":", 1)[1]
            parts.append((f"({count}) ", PALETTE["metadata"]))
        elif status == "cached":
            parts.append(("(cached) ", PALETTE["metadata"]))
        elif status == "empty":
            parts.append(("(no results) ", PALETTE["metadata"]))
    return Text.assemble(*parts)


def _summary_line(state: _AppState) -> Text:
    """Run-summary after fetch completes (M5).

    `2 of 3 sources · 47 results · 1.8s · YTS empty` — failed/empty sources
    are listed at the end; healthy hits are folded into the count.
    """
    progress = state.source_progress
    n_total = len(progress) or 0
    n_ok = sum(1 for s in progress.values() if s.startswith("ok:") or s == "cached")
    n_results = len(_all_results())
    failed = [n for n, s in progress.items() if s == "empty"]

    bits = []
    if n_ok == n_total:
        bits.append(f"{n_total} sources")
    else:
        bits.append(f"{n_ok} of {n_total} sources")
    bits.append(f"{n_results} results")
    bits.append(f"{state.fetch_elapsed:.1f}s")
    if failed:
        bits.append(f"{', '.join(failed)} empty")
    return Text("  ·  ".join(bits) + f"  —  '{_state.query}'", style=PALETTE["metadata"])


def render_header(state: _AppState):
    if state.mode == LOADING:
        verb = Spinner("dots", text=Text(state.current_verb + "…", style=PALETTE["headline"]))
        return Group(_render_progress_strip(state), verb)
    if state.mode == FILTER:
        return Group(
            _summary_line(state),
            Text.assemble(
                ("Filter: ", PALETTE["headline"]),
                (f"/{state.filter_text}", PALETTE["accent"]),
                ("_", PALETTE["blink"]),
            ),
        )
    if state.mode == RESULTS:
        return _summary_line(state)
    return Text(f"torrent-hound — '{_state.query}'", style=PALETTE["headline"])


def _table_window(state: _AppState, rows: list[dict]) -> tuple[list[dict], int]:
    """Slice `rows` to fit the current terminal body, centred on the selection.

    Returns (windowed_rows, start_offset). `start_offset` is the index in the
    full list at which the window begins — used to compute absolute row numbers.
    """
    # Body height ≈ terminal height minus reserved chrome:
    # header (2) + table-header (1) + toast (1) + footer (1) + padding fudge (1).
    body_height = max(1, _console.size.height - 6)
    if len(rows) <= body_height:
        return rows, 0
    start = state.selected_idx - body_height // 2
    start = max(0, min(start, len(rows) - body_height))
    return rows[start:start + body_height], start


def render_table(state: _AppState) -> Table:
    rows = _visible_results(state)
    windowed, start = _table_window(state, rows)
    total = len(rows)
    suffix = f" (showing {start + 1}-{start + len(windowed)} of {total})" if start > 0 or len(windowed) < total else ""
    table = Table(
        title=Text(f"results{suffix}", style=PALETTE["metadata"]) if suffix else None,
        header_style=PALETTE["err"],
        padding=(0, 1),
        show_lines=False,
        expand=True,
    )
    table.add_column("No", justify="left", width=4)
    table.add_column("Source", justify="left", width=6, style=PALETTE["metadata"])
    table.add_column("Name", justify="left", no_wrap=True)
    table.add_column("Size", justify="right", width=10)
    table.add_column("S", justify="right", width=6)
    table.add_column("L", justify="right", width=5)
    table.add_column("S/L", justify="right", width=5)
    for i, r in enumerate(windowed):
        absolute_idx = start + i
        style = PALETTE["accent"] if absolute_idx == state.selected_idx else ""
        table.add_row(
            str(absolute_idx + 1),
            r.get("source", ""),
            re.sub(r'[^\x20-\x7E]', '', r.get("name", ""))[:80],
            r.get("size", ""),
            str(r.get("seeders", "")),
            str(r.get("leechers", "")),
            str(r.get("ratio", "")),
            style=style,
        )
    return table


def render_empty_state(state: _AppState) -> Text:
    """N2 — friendlier message than an empty table."""
    if not _all_results():
        return Text(
            "No scents on that trail. Try broader terms, or add quality (1080p, 720p).",
            style=PALETTE["metadata"],
        )
    # Filter narrowed everything away
    return Text(
        f"No matches for '{state.filter_text}'. Esc to clear filter.",
        style=PALETTE["metadata"],
    )


def render_body(state: _AppState):
    if not _visible_results(state) and state.mode != LOADING:
        return render_empty_state(state)
    return render_table(state)


def render_toast(state: _AppState) -> Text:
    return Text(state.toast or "", style=PALETTE["ok"])


# Mode-aware footer key hints. M3 from the UX polish spec — the footer
# adapts to the screen the user is on rather than dumping a static legend.
_FOOTER_HINTS = {
    LOADING:    "q quit",
    RESULTS:    "↑↓ move · enter/c copy · o open · d send · s seedr · r real-debrid · / filter · q quit",
    FILTER:     "type to narrow · enter accept · esc cancel",
    RD_PICKER:  "0-9 pick · a all · enter confirm · esc cancel",
    RD_WAITING: "⏳ waiting on Debrid · esc cancel",
    HELP:       "any key to dismiss",
}


def render_footer(state: _AppState) -> Text:
    return Text(_FOOTER_HINTS.get(state.mode, ""), style=PALETTE["metadata"])


def render(state: _AppState) -> Layout:
    layout = _build_layout()
    layout["header"].update(render_header(state))
    layout["body"].update(render_body(state))
    layout["toast"].update(render_toast(state))
    layout["footer"].update(render_footer(state))
    return layout


# ── entry ──────────────────────────────────────────────────────────────
def _rotate_verb(state: _AppState) -> None:
    """Swap to a fresh random verb if the rotate window has elapsed."""
    now = time.monotonic()
    if now - state.verb_set_at >= VERB_ROTATE_SECONDS:
        state.current_verb = random.choice(SEARCH_VERBS)
        state.verb_set_at = now


def _kick_off_fetch(state: _AppState) -> threading.Thread:
    """Launch searchAllSites in a worker; flip mode to RESULTS when done."""
    def _on_progress(name: str, status: str) -> None:
        # Dict updates on a single key are atomic under the GIL — no lock needed.
        state.source_progress[name] = status

    def _worker() -> None:
        try:
            searchAllSites(_state.query, quiet_mode=True, progress_callback=_on_progress)
        finally:
            state.fetch_elapsed = time.monotonic() - state.fetch_started_at
            state.mode = RESULTS

    state.fetch_started_at = time.monotonic()
    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    return thread


def run_app() -> None:
    """Entry point for interactive mode. Replaces the old REPL `while` loop."""
    if not sys.stdin.isatty():
        # Piped stdin can't drive cbreak. Fall back to a non-interactive
        # message — caller should use --quiet / --json for scriptable output.
        print(
            "torrent-hound interactive mode requires a TTY. "
            "Use --quiet or --json for scriptable output."
        )
        return

    state = _AppState()
    state.current_verb = random.choice(SEARCH_VERBS)
    state.verb_set_at = time.monotonic()

    with cbreak(), Live(render(state), refresh_per_second=20, screen=True) as live:
        _kick_off_fetch(state)
        while True:
            # Poll stdin with timeout so the verb can rotate even with no input.
            rlist, _w, _x = select.select([sys.stdin], [], [], 0.1)
            if rlist:
                key = read_key()
                if not handle_key(state, key):
                    break
            if state.rd_request_entry is not None:
                _run_rd_suspended(live, state)
            if state.mode == LOADING:
                _rotate_verb(state)
            _expire_toast(state)
            live.update(render(state))


def _run_rd_suspended(live: Live, state: _AppState) -> None:
    """Drop out of the Live render so _cmd_rd's prints/inputs can drive the
    terminal directly, then restore the Live screen on completion. First-ship
    integration; a fully-native RD picker lands in a later iteration."""
    entry = state.rd_request_entry
    state.rd_request_entry = None
    live.stop()
    # Restore the cbreak'd terminal to cooked mode so input() inside _cmd_rd
    # works normally; re-enter cbreak when Live restarts.
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    try:
        # cooked mode for _cmd_rd
        cooked = termios.tcgetattr(fd)
        # tcgetattr returns the current attrs; we want canonical mode + echo.
        # Easier: temporarily restore the attrs that were set BEFORE cbreak() —
        # we don't have those here, so ask termios for sane defaults.
        cooked[3] |= termios.ICANON | termios.ECHO  # lflag
        termios.tcsetattr(fd, termios.TCSADRAIN, cooked)
        try:
            _cmd_rd(entry)
        except Exception as e:  # noqa: BLE001 — defence; RD path has many failure modes
            print(f"Real-Debrid error: {e}")
        input("\n[press enter to return to torrent-hound]")
        _set_toast(state, "Real-Debrid action complete")
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)
        live.start()
