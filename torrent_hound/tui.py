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

from rich.console import Group
from rich.live import Live
from rich.text import Text


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


def _render_placeholder() -> Group:
    return Group(
        Text("torrent-hound — TUI skeleton", style="bold"),
        Text("Real screens land in subsequent commits. Press q to quit.", style="dim"),
    )


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

    with cbreak(), Live(_render_placeholder(), refresh_per_second=20, screen=True):
        while True:
            key = read_key()
            if key == "q":
                break
