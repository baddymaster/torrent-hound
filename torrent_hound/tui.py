"""Terminal UI for torrent-hound's interactive mode.

Single-screen rich.live app. Replaces the old REPL `Enter command :` loop
with arrow-key navigation, mode-aware footer, live filtering, and inline
RD integration.

Architecture + screen model documented in
tasks/specs/2026-04-25-tui-implementation-spec.md. This file is being
filled in incrementally, one commit per step.
"""
from __future__ import annotations

import re
import sys
import termios
import tty
import webbrowser
from contextlib import contextmanager
from dataclasses import dataclass, field

import pyperclip
from rich.layout import Layout
from rich.live import Live
from rich.table import Table
from rich.text import Text

from torrent_hound import state as _state
from torrent_hound.sources import searchAllSites

# ── modes ──────────────────────────────────────────────────────────────
LOADING = "loading"
RESULTS = "results"
FILTER = "filter"
RD_PICKER = "rd_picker"
RD_WAITING = "rd_waiting"
HELP = "help"


@dataclass
class _AppState:
    """All TUI state in one place. Render is a pure function of this."""
    mode: str = RESULTS
    selected_idx: int = 0
    filter_text: str = ""
    toast: str | None = None
    # Per-source progress, populated during loading. Mode determines visibility.
    source_progress: dict = field(default_factory=dict)


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
                state.toast = _RESULTS_ACTIONS[key](entry)
        elif key == "r":
            state.toast = "Real-Debrid integration lands in step 8"

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


def render_header(state: _AppState) -> Text:
    if state.mode == FILTER:
        return Text.assemble(
            ("torrent-hound — ", "bold"),
            (f"/{state.filter_text}", "bold #ffb84d"),
            ("_", "bold #ffb84d blink"),
        )
    return Text(f"torrent-hound — '{_state.query}'", style="bold")


def render_table(state: _AppState) -> Table:
    rows = _visible_results(state)
    table = Table(header_style="red", padding=(0, 1), show_lines=False, expand=True)
    table.add_column("No", justify="left", width=3)
    table.add_column("Name", justify="left", no_wrap=True)
    table.add_column("Size", justify="right", width=10)
    table.add_column("S", justify="right", width=6)
    table.add_column("L", justify="right", width=5)
    table.add_column("S/L", justify="right", width=5)
    if not rows:
        table.add_row("", "(no results)", "", "", "", "")
        return table
    for i, r in enumerate(rows):
        style = "bold #ffb84d" if i == state.selected_idx else ""
        table.add_row(
            str(i + 1),
            re.sub(r'[^\x20-\x7E]', '', r.get("name", ""))[:80],
            r.get("size", ""),
            str(r.get("seeders", "")),
            str(r.get("leechers", "")),
            str(r.get("ratio", "")),
            style=style,
        )
    return table


def render_body(state: _AppState):
    return render_table(state)


def render_toast(state: _AppState) -> Text:
    return Text(state.toast or "", style="green")


def render_footer(state: _AppState) -> Text:
    return Text(
        "↑↓ move · enter/c copy · o open page · d send to client · s seedr · q quit",
        style="dim",
    )


def render(state: _AppState) -> Layout:
    layout = _build_layout()
    layout["header"].update(render_header(state))
    layout["body"].update(render_body(state))
    layout["toast"].update(render_toast(state))
    layout["footer"].update(render_footer(state))
    return layout


# ── entry ──────────────────────────────────────────────────────────────
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

    # Synchronous fetch for now; a worker-thread + progress strip lands in step 6.
    searchAllSites(_state.query)

    state = _AppState()
    with cbreak(), Live(render(state), refresh_per_second=20, screen=True) as live:
        while True:
            key = read_key()
            if not handle_key(state, key):
                break
            live.update(render(state))
