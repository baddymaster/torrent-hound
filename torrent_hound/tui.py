"""Terminal UI for torrent-hound's interactive mode.

Single-screen rich.live app. Replaces the old REPL `Enter command :` loop
with arrow-key navigation, mode-aware footer, live filtering, and inline
RD integration.

Architecture + screen model documented in
tasks/specs/2026-04-25-tui-implementation-spec.md. This file is being
filled in incrementally, one commit per step.
"""
from __future__ import annotations

import sys
import termios
import tty
from contextlib import contextmanager
from dataclasses import dataclass, field

from rich.layout import Layout
from rich.live import Live
from rich.text import Text

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


def handle_key(state: _AppState, key: str) -> bool:
    """Mutates state in-place. Returns False to break the event loop.

    Mode-specific dispatch lives here; per-mode handlers added in later commits.
    """
    if key == "q":
        return False
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
    return Text("torrent-hound — TUI", style="bold")


def render_body(state: _AppState) -> Text:
    return Text("(results table lands in step 3)", style="dim")


def render_toast(state: _AppState) -> Text:
    return Text(state.toast or "")


def render_footer(state: _AppState) -> Text:
    return Text("q quit", style="dim")


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

    state = _AppState()
    with cbreak(), Live(render(state), refresh_per_second=20, screen=True) as live:
        while True:
            key = read_key()
            if not handle_key(state, key):
                break
            live.update(render(state))
