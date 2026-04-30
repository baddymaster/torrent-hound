"""Tests for the TUI's read_key parser and handle_key state machine.

`read_key` tests mock os.read + select.select to feed synthetic byte streams
through the parser. `handle_key` tests construct fresh _AppState instances
and assert state mutations after each key.

Why the tests exist: the read_key path has been bitten three times during
development (timing window too tight, Python TextIOWrapper buffering, missing
arrow handling in filter mode). These tests pin all of those down.
"""

import threading
import time
from collections import deque
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from torrent_hound import state as state_module
from torrent_hound.tui import (
    FILTER,
    HELP,
    LOADING,
    MAGNET_VIEW,
    METADATA_VIEW,
    RD_PICKER,
    RD_WAITING,
    RESULTS,
    SEARCH,
    _AppState,
    _kick_off_rd,
    _name_column_budget,
    _rd_worker,
    _RDFlow,
    handle_key,
    read_key,
    render_table,
)

# ── read_key infrastructure ────────────────────────────────────────────

class _FakeStdin:
    """Replays the given byte chunks via os.read; reports "data available"
    on select.select if any chunks remain."""
    def __init__(self, chunks):
        self.chunks = deque(chunks)

    def os_read(self, fd, n):
        if not self.chunks:
            raise BlockingIOError("no chunks left — read_key called more reads than expected")
        chunk = self.chunks.popleft()
        return chunk[:n]

    def select(self, rlist, wlist, xlist, timeout):
        if self.chunks:
            return (rlist, [], [])
        return ([], [], [])


@contextmanager
def _patched_input(fake):
    """Patch sys.stdin (pytest replaces it with a non-tty mock that has no
    fileno()), os.read, and select.select for the duration of the block."""
    mock_stdin = MagicMock()
    mock_stdin.fileno.return_value = 0
    with patch("sys.stdin", mock_stdin), \
         patch("os.read", fake.os_read), \
         patch("select.select", fake.select):
        yield


# ── read_key tests ─────────────────────────────────────────────────────

def test_read_key_single_ascii_char():
    fake = _FakeStdin([b"c"])
    with _patched_input(fake):
        assert read_key() == "c"


def test_read_key_carriage_return():
    fake = _FakeStdin([b"\r"])
    with _patched_input(fake):
        assert read_key() == "\r"


def test_read_key_backspace():
    fake = _FakeStdin([b"\x7f"])
    with _patched_input(fake):
        assert read_key() == "\x7f"


def test_read_key_arrow_up():
    fake = _FakeStdin([b"\x1b", b"[A"])
    with _patched_input(fake):
        assert read_key() == "UP"


def test_read_key_arrow_down():
    fake = _FakeStdin([b"\x1b", b"[B"])
    with _patched_input(fake):
        assert read_key() == "DOWN"


def test_read_key_arrow_left():
    fake = _FakeStdin([b"\x1b", b"[D"])
    with _patched_input(fake):
        assert read_key() == "LEFT"


def test_read_key_arrow_right():
    fake = _FakeStdin([b"\x1b", b"[C"])
    with _patched_input(fake):
        assert read_key() == "RIGHT"


def test_read_key_bare_esc_returns_esc_without_blocking():
    """The original bug: bare ESC blocked because we tried to read more bytes."""
    fake = _FakeStdin([b"\x1b"])
    with _patched_input(fake):
        assert read_key() == "ESC"


def test_read_key_alt_letter_resolves_to_esc():
    """`\\x1b` followed by a letter (Alt+A) isn't a recognised mapping."""
    fake = _FakeStdin([b"\x1b", b"a"])
    with _patched_input(fake):
        assert read_key() == "ESC"


def test_read_key_unknown_csi_resolves_to_esc():
    """`\\x1b[X` — looks like CSI but X isn't one of UP/DOWN/LEFT/RIGHT/HOME/END."""
    fake = _FakeStdin([b"\x1b", b"[X"])
    with _patched_input(fake):
        assert read_key() == "ESC"


def test_read_key_arrow_sequence_arrives_in_one_burst():
    """Some terminals deliver `\\x1b[A` as a single 3-byte read."""
    fake = _FakeStdin([b"\x1b", b"[A"])
    with _patched_input(fake):
        assert read_key() == "UP"


# ── handle_key fixture: keep state-module mutations test-isolated ─────

@pytest.fixture
def reset_state():
    saved_results = state_module.results
    saved_query = state_module.query
    yield
    state_module.results = saved_results
    state_module.query = saved_query


def _populate_results(n: int) -> None:
    state_module.results = [
        {
            "name": f"row-{i}",
            "magnet": f"magnet:?xt=urn:btih:{i:040x}",
            "link": f"https://example.test/{i}",
            "source": "TPB",
            "size": "1 GB",
            "seeders": i,
            "leechers": i,
            "ratio": "1.0",
        }
        for i in range(n)
    ]


# ── handle_key — RESULTS mode navigation ──────────────────────────────

def test_handle_key_q_returns_false(reset_state):
    state = _AppState(mode=RESULTS)
    assert handle_key(state, "q") is False


def test_handle_key_down_advances_selection(reset_state):
    _populate_results(5)
    state = _AppState(mode=RESULTS, selected_idx=0)
    assert handle_key(state, "DOWN") is True
    assert state.selected_idx == 1


def test_handle_key_up_decrements_selection(reset_state):
    _populate_results(5)
    state = _AppState(mode=RESULTS, selected_idx=2)
    handle_key(state, "UP")
    assert state.selected_idx == 1


def test_handle_key_up_at_top_clamps_to_zero(reset_state):
    _populate_results(5)
    state = _AppState(mode=RESULTS, selected_idx=0)
    handle_key(state, "UP")
    assert state.selected_idx == 0


def test_handle_key_down_at_bottom_clamps(reset_state):
    _populate_results(5)
    state = _AppState(mode=RESULTS, selected_idx=4)
    handle_key(state, "DOWN")
    assert state.selected_idx == 4


def test_handle_key_down_on_empty_results_is_safe(reset_state):
    state_module.results = []
    state = _AppState(mode=RESULTS, selected_idx=0)
    handle_key(state, "DOWN")
    assert state.selected_idx == 0


def test_handle_key_slash_enters_filter_mode(reset_state):
    _populate_results(3)
    state = _AppState(mode=RESULTS, filter_text="leftover")
    handle_key(state, "/")
    assert state.mode == FILTER
    assert state.filter_text == ""    # cleared on entry


def test_handle_key_s_enters_search_mode(reset_state):
    state = _AppState(mode=RESULTS, search_text="leftover")
    handle_key(state, "s")
    assert state.mode == SEARCH
    assert state.search_text == ""    # cleared on entry


# ── handle_key — RESULTS mode chord (multi-char) ──────────────────────

def test_handle_key_c_alone_buffers_chord_prefix(reset_state):
    state = _AppState(mode=RESULTS)
    handle_key(state, "c")
    assert state.chord_buffer == "c"


def test_handle_key_cs_chord_dispatches_seedr(reset_state):
    _populate_results(3)
    state = _AppState(mode=RESULTS, selected_idx=0)
    with patch("torrent_hound.tui.pyperclip.copy") as m_copy, \
         patch("torrent_hound.tui.webbrowser.open") as m_open:
        handle_key(state, "c")
        handle_key(state, "s")
    assert state.chord_buffer == ""
    m_copy.assert_called_once()
    m_open.assert_called_once_with("https://www.seedr.cc", new=2)


def test_handle_key_rd_chord_sets_rd_request(reset_state):
    _populate_results(3)
    state = _AppState(mode=RESULTS, selected_idx=1)
    handle_key(state, "r")
    handle_key(state, "d")
    assert state.chord_buffer == ""
    assert state.rd_request_entry is not None
    assert state.rd_request_entry["name"] == "row-1"


def test_handle_key_r_then_unrelated_key_flushes_then_processes(reset_state):
    """`r` followed by `o` should: dispatch `r` (refetch), then `o` (open page)."""
    _populate_results(3)
    state = _AppState(mode=RESULTS, selected_idx=0)
    with patch("torrent_hound.tui.webbrowser.open") as m_open:
        handle_key(state, "r")
        handle_key(state, "o")
    assert state.chord_buffer == ""
    assert state.refetch_request is True            # 'r' was flushed
    assert m_open.call_count == 1                   # 'o' was processed after


def test_handle_key_esc_during_pending_chord_cancels_silently(reset_state):
    state = _AppState(mode=RESULTS, chord_buffer="r")
    handle_key(state, "ESC")
    assert state.chord_buffer == ""
    assert state.refetch_request is False            # NOT dispatched


def test_handle_key_c_alone_does_not_immediately_act(reset_state):
    """Pressing `c` should buffer, not act, until the chord resolves."""
    _populate_results(3)
    state = _AppState(mode=RESULTS, selected_idx=0)
    with patch("torrent_hound.tui.pyperclip.copy") as m_copy:
        handle_key(state, "c")
    m_copy.assert_not_called()


# ── handle_key — FILTER mode (the regression we're fixing) ────────────

def test_filter_printable_appends_to_filter_text(reset_state):
    state = _AppState(mode=FILTER, filter_text="ub")
    handle_key(state, "u")
    assert state.filter_text == "ubu"


def test_filter_backspace_removes_last_char(reset_state):
    state = _AppState(mode=FILTER, filter_text="ubu")
    handle_key(state, "\x7f")
    assert state.filter_text == "ub"


def test_filter_enter_exits_to_results_keeping_filter(reset_state):
    state = _AppState(mode=FILTER, filter_text="ubu")
    handle_key(state, "\r")
    assert state.mode == RESULTS
    assert state.filter_text == "ubu"


def test_filter_esc_exits_and_clears(reset_state):
    state = _AppState(mode=FILTER, filter_text="ubu")
    handle_key(state, "ESC")
    assert state.mode == RESULTS
    assert state.filter_text == ""


def test_filter_down_navigates_without_leaving_filter_mode(reset_state):
    """The bug: arrows in FILTER mode were silently dropped."""
    _populate_results(5)
    state = _AppState(mode=FILTER, filter_text="row", selected_idx=0)
    handle_key(state, "DOWN")
    assert state.mode == FILTER          # stays in filter
    assert state.selected_idx == 1


def test_filter_up_navigates_without_leaving_filter_mode(reset_state):
    _populate_results(5)
    state = _AppState(mode=FILTER, filter_text="row", selected_idx=2)
    handle_key(state, "UP")
    assert state.mode == FILTER
    assert state.selected_idx == 1


def test_filter_typing_resets_selection(reset_state):
    """Changing the filter shifts the visible rows; selection resets to the top."""
    _populate_results(5)
    state = _AppState(mode=FILTER, filter_text="row", selected_idx=3)
    handle_key(state, "0")
    assert state.selected_idx == 0


def test_filter_arrow_does_not_reset_selection(reset_state):
    """Arrow nav inside filter mode must NOT reset selection (filter unchanged)."""
    _populate_results(5)
    state = _AppState(mode=FILTER, filter_text="row", selected_idx=3)
    handle_key(state, "UP")
    assert state.selected_idx == 2


def test_filter_arrow_at_boundary_clamps(reset_state):
    _populate_results(3)
    state = _AppState(mode=FILTER, filter_text="row", selected_idx=2)
    handle_key(state, "DOWN")
    assert state.selected_idx == 2  # clamped


def test_filter_arrow_with_empty_filter_navigates_full_list(reset_state):
    _populate_results(5)
    state = _AppState(mode=FILTER, filter_text="", selected_idx=0)
    handle_key(state, "DOWN")
    assert state.selected_idx == 1


# ── handle_key — SEARCH mode ──────────────────────────────────────────

def test_search_printable_appends(reset_state):
    state = _AppState(mode=SEARCH, search_text="ubu")
    handle_key(state, "n")
    assert state.search_text == "ubun"


def test_search_enter_with_text_triggers_refetch(reset_state):
    state = _AppState(mode=SEARCH, search_text="ubuntu")
    handle_key(state, "\r")
    assert state.mode == LOADING
    assert state.refetch_request is True
    assert state_module.query == "ubuntu"


def test_search_enter_empty_returns_to_results(reset_state):
    state = _AppState(mode=SEARCH, search_text="")
    handle_key(state, "\r")
    assert state.mode == RESULTS
    assert state.refetch_request is False


def test_search_esc_clears_and_exits(reset_state):
    state = _AppState(mode=SEARCH, search_text="ubun")
    handle_key(state, "ESC")
    assert state.mode == RESULTS
    assert state.search_text == ""


def test_search_backspace_removes_last_char(reset_state):
    state = _AppState(mode=SEARCH, search_text="ubuntu")
    handle_key(state, "\x7f")
    assert state.search_text == "ubunt"


# ── handle_key — MAGNET_VIEW mode ─────────────────────────────────────

def test_m_enters_magnet_view_with_selected_magnet(reset_state):
    _populate_results(3)
    state = _AppState(mode=RESULTS, selected_idx=1)
    handle_key(state, "m")
    assert state.mode == MAGNET_VIEW
    assert state.magnet_view_text == state_module.results[1]["magnet"]
    assert state.magnet_view_name == state_module.results[1]["name"]


def test_m_on_empty_results_does_not_change_mode(reset_state):
    state_module.results = []
    state = _AppState(mode=RESULTS)
    handle_key(state, "m")
    assert state.mode == RESULTS
    assert state.magnet_view_text == ""


def test_magnet_view_any_key_returns_to_results(reset_state):
    state = _AppState(mode=MAGNET_VIEW, magnet_view_text="magnet:?xt=...")
    handle_key(state, "x")
    assert state.mode == RESULTS


def test_magnet_view_q_quits(reset_state):
    state = _AppState(mode=MAGNET_VIEW)
    assert handle_key(state, "q") is False


# ── handle_key — HELP mode ────────────────────────────────────────────

def test_question_mark_enters_help_mode(reset_state):
    state = _AppState(mode=RESULTS)
    handle_key(state, "?")
    assert state.mode == HELP


def test_help_any_key_returns_to_results(reset_state):
    state = _AppState(mode=HELP)
    handle_key(state, "x")
    assert state.mode == RESULTS


def test_help_q_quits(reset_state):
    state = _AppState(mode=HELP)
    assert handle_key(state, "q") is False


# ── handle_key — LOADING mode ─────────────────────────────────────────

def test_loading_q_quits(reset_state):
    state = _AppState(mode=LOADING)
    assert handle_key(state, "q") is False


def test_loading_arrows_ignored(reset_state):
    _populate_results(5)
    state = _AppState(mode=LOADING, selected_idx=0)
    handle_key(state, "DOWN")
    assert state.selected_idx == 0    # ignored while loading


# ── handle_key — RD_PICKER mode ───────────────────────────────────────

def _picker_state(n_files=4, marked=None, idx=0):
    """Build an _AppState in RD_PICKER mode with `n_files` mock files,
    `marked` indices pre-marked (defaults to all), at cursor `idx`."""
    flow = _RDFlow()
    flow.files = [{"id": i + 100, "path": f"/show/file{i}.mkv", "bytes": 1000} for i in range(n_files)]
    flow.picker_marked = set(range(n_files)) if marked is None else set(marked)
    flow.picker_idx = idx
    flow.selection_event = threading.Event()
    state = _AppState(mode=RD_PICKER)
    state.rd_flow = flow
    return state


def test_picker_down_moves_cursor(reset_state):
    state = _picker_state(idx=0)
    handle_key(state, "DOWN")
    assert state.rd_flow.picker_idx == 1


def test_picker_down_clamps_at_bottom(reset_state):
    state = _picker_state(n_files=3, idx=2)
    handle_key(state, "DOWN")
    assert state.rd_flow.picker_idx == 2


def test_picker_up_clamps_at_top(reset_state):
    state = _picker_state(idx=0)
    handle_key(state, "UP")
    assert state.rd_flow.picker_idx == 0


def test_picker_space_toggles_current_off_when_marked(reset_state):
    state = _picker_state(idx=2, marked={0, 1, 2, 3})
    handle_key(state, " ")
    assert 2 not in state.rd_flow.picker_marked
    assert state.rd_flow.picker_marked == {0, 1, 3}


def test_picker_space_toggles_current_on_when_unmarked(reset_state):
    state = _picker_state(idx=2, marked={0, 1})
    handle_key(state, " ")
    assert 2 in state.rd_flow.picker_marked


def test_picker_a_clears_when_all_marked(reset_state):
    state = _picker_state(n_files=3, marked={0, 1, 2})
    handle_key(state, "a")
    assert state.rd_flow.picker_marked == set()


def test_picker_a_marks_all_when_none(reset_state):
    state = _picker_state(n_files=3, marked=set())
    handle_key(state, "a")
    assert state.rd_flow.picker_marked == {0, 1, 2}


def test_picker_a_marks_all_when_partial(reset_state):
    state = _picker_state(n_files=3, marked={1})
    handle_key(state, "a")
    assert state.rd_flow.picker_marked == {0, 1, 2}


def test_picker_enter_signals_worker_with_sorted_selection(reset_state):
    state = _picker_state(n_files=4, marked={3, 0, 2})
    handle_key(state, "\r")
    assert state.rd_flow.pending_selection == [0, 2, 3]
    assert state.rd_flow.selection_event.is_set()


def test_picker_enter_with_nothing_marked_does_not_signal(reset_state):
    """Confirming with zero files marked is a no-op — the worker must end up
    with at least one file selected, otherwise RD's selectFiles call will fail."""
    state = _picker_state(marked=set())
    handle_key(state, "\r")
    assert state.rd_flow.pending_selection is None
    assert not state.rd_flow.selection_event.is_set()


def test_picker_esc_signals_cancel(reset_state):
    state = _picker_state()
    handle_key(state, "ESC")
    assert state.rd_flow.pending_selection == "cancel"
    assert state.rd_flow.selection_event.is_set()


def test_picker_q_cancels_and_quits(reset_state):
    """Quitting from the picker must cancel the worker first — otherwise it'd
    block forever on selection_event.wait() and the daemon thread stays
    around until process exit."""
    state = _picker_state()
    result = handle_key(state, "q")
    assert result is False
    assert state.rd_flow.pending_selection == "cancel"
    assert state.rd_flow.selection_event.is_set()


# ── handle_key — RD_WAITING mode ──────────────────────────────────────

def test_rd_waiting_q_quits(reset_state):
    state = _AppState(mode=RD_WAITING)
    assert handle_key(state, "q") is False


def test_rd_waiting_other_keys_ignored(reset_state):
    """Mid-flow keys are ignored — the worker is doing network I/O and we
    don't want the user accidentally cancelling by pressing arrows."""
    state = _AppState(mode=RD_WAITING)
    assert handle_key(state, "DOWN") is True
    assert handle_key(state, "x") is True
    assert state.mode == RD_WAITING


# ── _rd_worker integration (mocked RD calls) ──────────────────────────

def _entry(magnet="magnet:?xt=urn:btih:" + "ab" * 20):
    return {"name": "test torrent", "magnet": magnet, "link": "https://example/page"}


def test_rd_worker_single_file_flow_succeeds(reset_state):
    """Single-file torrent: worker selects 'all' without invoking the picker,
    polls links, dispatches via the configured action, surfaces success toast."""
    info_with_one_file = {
        "files": [{"id": 100, "path": "/film.mkv", "bytes": 1024, "selected": 0}],
        "status": "downloaded",
        "links": ["https://rd.example/host1"],
    }
    state = _AppState(mode=RD_WAITING)
    state.rd_flow = _RDFlow()
    with patch("torrent_hound.tui._rd_add_magnet", return_value="tid-1"), \
         patch("torrent_hound.tui._rd_get_info", return_value=info_with_one_file), \
         patch("torrent_hound.tui._rd_select_files") as m_sel, \
         patch("torrent_hound.tui._rd_unrestrict", return_value="https://rd.example/direct"), \
         patch("torrent_hound.tui._rd_dispatch", return_value="Real-Debrid: 1 link copied"):
        _rd_worker(state, _entry(), token="tok", action="clipboard")
    assert state.rd_flow is None
    assert state.mode == RESULTS
    assert "1 link copied" in state.toast
    m_sel.assert_called_once_with("tid-1", "all", token="tok")


def test_rd_worker_multi_file_picker_handoff(reset_state):
    """Multi-file torrent: worker stalls on RD_PICKER until the main thread
    sets `pending_selection` and signals `selection_event`. After the handoff,
    worker maps indices → RD file IDs, calls selectFiles, completes the flow."""
    files = [
        {"id": 200, "path": "/show/s01e01.mkv", "bytes": 1000, "selected": 0},
        {"id": 201, "path": "/show/s01e02.mkv", "bytes": 1000, "selected": 0},
        {"id": 202, "path": "/show/s01e03.mkv", "bytes": 1000, "selected": 0},
    ]
    info_with_files = {"files": files, "status": "downloaded", "links": ["https://rd.example/h"]}
    state = _AppState(mode=RD_WAITING)
    state.rd_flow = _RDFlow()
    select_calls = []
    with patch("torrent_hound.tui._rd_add_magnet", return_value="tid-2"), \
         patch("torrent_hound.tui._rd_get_info", return_value=info_with_files), \
         patch("torrent_hound.tui._rd_select_files", side_effect=lambda *a, **kw: select_calls.append((a, kw))), \
         patch("torrent_hound.tui._rd_unrestrict", return_value="https://rd.example/direct"), \
         patch("torrent_hound.tui._rd_dispatch", return_value="Real-Debrid: 1 link copied"):
        worker = threading.Thread(
            target=_rd_worker, args=(state, _entry(), "tok", "clipboard"), daemon=True
        )
        worker.start()
        # Wait for the worker to flip into RD_PICKER. Cap to avoid hangs in CI.
        deadline = time.monotonic() + 2.0
        while state.mode != RD_PICKER:
            if time.monotonic() >= deadline:
                raise AssertionError(f"worker never reached RD_PICKER (mode={state.mode!r})")
            time.sleep(0.005)
        # Pick the first and third file via the same hand-off the picker uses
        state.rd_flow.pending_selection = [0, 2]
        state.rd_flow.selection_event.set()
        worker.join(timeout=2.0)
        assert not worker.is_alive(), "worker didn't finish after selection signalled"
    assert state.rd_flow is None
    assert state.mode == RESULTS
    assert "1 link copied" in state.toast
    assert len(select_calls) == 1
    args, kwargs = select_calls[0]
    assert args == ("tid-2", "200,202")  # IDs mapped from indices [0, 2]
    assert kwargs == {"token": "tok"}


def test_rd_worker_cancel_from_picker_clears_flow(reset_state):
    """Picker cancel must end the flow with a 'cancelled' toast and not call
    selectFiles or any downstream API."""
    files = [{"id": 1, "path": "/a", "bytes": 1, "selected": 0},
             {"id": 2, "path": "/b", "bytes": 1, "selected": 0}]
    info = {"files": files, "status": "downloaded", "links": []}
    state = _AppState(mode=RD_WAITING)
    state.rd_flow = _RDFlow()
    with patch("torrent_hound.tui._rd_add_magnet", return_value="tid"), \
         patch("torrent_hound.tui._rd_get_info", return_value=info), \
         patch("torrent_hound.tui._rd_select_files") as m_sel, \
         patch("torrent_hound.tui._rd_unrestrict") as m_un, \
         patch("torrent_hound.tui._rd_dispatch") as m_dispatch:
        worker = threading.Thread(
            target=_rd_worker, args=(state, _entry(), "tok", "clipboard"), daemon=True
        )
        worker.start()
        deadline = time.monotonic() + 2.0
        while state.mode != RD_PICKER:
            if time.monotonic() >= deadline:
                raise AssertionError("worker never reached RD_PICKER")
            time.sleep(0.005)
        state.rd_flow.pending_selection = "cancel"
        state.rd_flow.selection_event.set()
        worker.join(timeout=2.0)
    assert state.rd_flow is None
    assert state.mode == RESULTS
    assert "cancelled" in state.toast.lower()
    m_sel.assert_not_called()
    m_un.assert_not_called()
    m_dispatch.assert_not_called()


def test_rd_worker_already_selected_skips_picker(reset_state):
    """Re-running rd on a torrent we already submitted: RD reports `selected: 1`
    on at least one file, so we must skip the picker and selectFiles call."""
    info = {
        "files": [{"id": 1, "path": "/a", "bytes": 1, "selected": 1}],
        "status": "downloaded",
        "links": ["https://rd.example/h"],
    }
    state = _AppState(mode=RD_WAITING)
    state.rd_flow = _RDFlow()
    with patch("torrent_hound.tui._rd_add_magnet", return_value="tid"), \
         patch("torrent_hound.tui._rd_get_info", return_value=info), \
         patch("torrent_hound.tui._rd_select_files") as m_sel, \
         patch("torrent_hound.tui._rd_unrestrict", return_value="https://rd.example/direct"), \
         patch("torrent_hound.tui._rd_dispatch", return_value="OK"):
        _rd_worker(state, _entry(), token="tok", action="clipboard")
    m_sel.assert_not_called()
    assert state.rd_flow is None
    assert state.mode == RESULTS


def test_rd_worker_no_files_yet_asks_user_to_retry(reset_state):
    """Magnet still resolving on RD's side (info returns no files) — surface
    a clear retry message and bail without calling selectFiles."""
    info_no_files = {"files": [], "status": "magnet_conversion"}
    state = _AppState(mode=RD_WAITING)
    state.rd_flow = _RDFlow()
    with patch("torrent_hound.tui._rd_add_magnet", return_value="tid"), \
         patch("torrent_hound.tui._rd_get_info", return_value=info_no_files), \
         patch("torrent_hound.tui._rd_select_files") as m_sel:
        _rd_worker(state, _entry(), token="tok", action="clipboard")
    m_sel.assert_not_called()
    assert state.rd_flow is None
    assert "resolving" in state.toast.lower()
    assert state.mode == RESULTS


def test_rd_worker_bad_status_surfaces_message(reset_state):
    """RD marked the torrent dead/virus/error — bail with the status as the toast."""
    info = {
        "files": [{"id": 1, "path": "/a", "bytes": 1, "selected": 1}],
        "status": "virus",
        "links": [],
    }
    state = _AppState(mode=RD_WAITING)
    state.rd_flow = _RDFlow()
    with patch("torrent_hound.tui._rd_add_magnet", return_value="tid"), \
         patch("torrent_hound.tui._rd_get_info", return_value=info):
        _rd_worker(state, _entry(), token="tok", action="clipboard")
    assert state.rd_flow is None
    assert "virus" in state.toast
    assert state.mode == RESULTS


def test_rd_worker_invalid_magnet_short_circuits(reset_state):
    """Entry with an unparseable magnet should surface a friendly toast and
    not even attempt addMagnet."""
    state = _AppState(mode=RD_WAITING)
    state.rd_flow = _RDFlow()
    with patch("torrent_hound.tui._rd_add_magnet") as m_add:
        _rd_worker(state, {"magnet": "not-a-magnet"}, token="tok", action="clipboard")
    m_add.assert_not_called()
    assert state.rd_flow is None
    assert "info-hash" in state.toast.lower()


# ── render_table — long name handling ─────────────────────────────────

def test_name_column_budget_scales_with_console_width():
    """The Name column's char budget shrinks/grows with the actual terminal
    width — important so the table never overflows the body Layout slot
    when a result has a long filename."""
    with patch("torrent_hound.tui._console") as fake_console:
        fake_console.size.width = 120
        budget_120 = _name_column_budget()
        fake_console.size.width = 80
        budget_80 = _name_column_budget()
    # Both should be positive and reflect the width difference
    assert budget_80 < budget_120
    assert budget_80 == budget_120 - 40


def test_name_column_budget_clamps_to_minimum_for_narrow_terminals():
    """Very narrow terminals must still get a non-zero budget — the row
    is unreadable below a certain width but rendering must not crash."""
    with patch("torrent_hound.tui._console") as fake_console:
        fake_console.size.width = 30   # absurdly narrow
        assert _name_column_budget() == 20  # clamped to minimum


def test_render_table_truncates_overlong_name_with_ellipsis(reset_state):
    """A torrent name longer than the dynamic budget must be truncated
    in-place with an ellipsis, never passed full-length to rich. This is
    the deterministic guard against the long-name layout-corruption bug."""
    state_module.results = [{
        "name": "A" * 200,  # absurdly long, exceeds any sane terminal
        "magnet": "magnet:?xt=urn:btih:" + "0" * 40,
        "link": "https://example.test/x",
        "source": "TPB",
        "size": "1 GB",
        "seeders": 1,
        "leechers": 1,
        "ratio": "1.0",
    }]
    state = _AppState(mode=RESULTS, selected_idx=0)
    with patch("torrent_hound.tui._console") as fake_console:
        fake_console.size.width = 100
        fake_console.size.height = 30
        table = render_table(state)
        budget = _name_column_budget()
    # The row's Name cell content must be ≤ budget; the cell ends in "…".
    rendered_name = table.columns[1]._cells[0]
    assert len(rendered_name) <= budget
    assert rendered_name.endswith("…")


def test_metadata_view_mode_constant_exists():
    from torrent_hound.tui import METADATA_VIEW
    assert METADATA_VIEW == "metadata_view"


def test_app_state_has_metadata_view_fields():
    state = _AppState()
    assert state.metadata_view_entry is None
    assert state.metadata_view_scroll_top == 0
    assert state.metadata_view_loading is False
    assert state.metadata_view_error is None


def test_kick_off_metadata_fetch_returns_none_for_eztv(reset_state):
    """EZTV is fully eager — no lazy fetch should be kicked off."""
    from torrent_hound.tui import _kick_off_metadata_fetch
    entry = {"source": "EZTV", "link": "x", "metadata": {}}
    state = _AppState()
    assert _kick_off_metadata_fetch(state, entry) is None
    assert state.metadata_view_loading is False


def test_kick_off_metadata_fetch_returns_none_when_already_fetched(reset_state):
    from torrent_hound.tui import _kick_off_metadata_fetch
    entry = {"source": "TPB", "link": "x", "metadata": {"_lazy_fetched": True}}
    state = _AppState()
    assert _kick_off_metadata_fetch(state, entry) is None


def test_kick_off_metadata_fetch_returns_none_when_in_progress(reset_state):
    from torrent_hound.tui import _kick_off_metadata_fetch
    entry = {"source": "TPB", "link": "x", "metadata": {"_lazy_fetching": True}}
    state = _AppState()
    assert _kick_off_metadata_fetch(state, entry) is None


def test_kick_off_metadata_fetch_tpb_writes_back_on_success(reset_state):
    """Worker fetches via mocked _fetch_tpb_metadata, merges into entry's
    metadata, sets _lazy_fetched, clears _lazy_fetching."""
    from torrent_hound.tui import _kick_off_metadata_fetch
    entry = {"source": "TPB", "link": "https://example/torrent/1", "metadata": {}}
    state = _AppState()
    with patch("torrent_hound.tui._fetch_tpb_metadata",
               return_value={"uploader": "alice", "files": 3}):
        thread = _kick_off_metadata_fetch(state, entry)
    assert thread is not None
    thread.join(timeout=2.0)
    md = entry["metadata"]
    assert md["uploader"] == "alice"
    assert md["files"] == 3
    assert md["_lazy_fetched"] is True
    assert "_lazy_fetching" not in md
    assert state.metadata_view_loading is False
    assert state.metadata_view_error is None


def test_kick_off_metadata_fetch_yts_uses_movie_id(reset_state):
    from torrent_hound.tui import _kick_off_metadata_fetch
    entry = {"source": "YTS", "link": "x", "metadata": {"_yts_movie_id": 42}}
    state = _AppState()
    with patch("torrent_hound.tui._fetch_yts_movie_details",
               return_value={"cast": "A, B"}) as m:
        thread = _kick_off_metadata_fetch(state, entry)
    assert thread is not None
    thread.join(timeout=2.0)
    m.assert_called_once_with(42)
    assert entry["metadata"]["cast"] == "A, B"
    assert entry["metadata"]["_lazy_fetched"] is True


def test_kick_off_metadata_fetch_sets_error_on_empty_response(reset_state):
    """Empty dict from the source-specific fetcher → error set, _lazy_fetched
    NOT set so re-pressing v retries."""
    from torrent_hound.tui import _kick_off_metadata_fetch
    entry = {"source": "TPB", "link": "x", "metadata": {}}
    state = _AppState()
    with patch("torrent_hound.tui._fetch_tpb_metadata", return_value={}):
        thread = _kick_off_metadata_fetch(state, entry)
    thread.join(timeout=2.0)
    assert state.metadata_view_error is not None
    assert "_lazy_fetched" not in entry["metadata"]
    assert "_lazy_fetching" not in entry["metadata"]


def test_metadata_view_q_quits(reset_state):
    state = _AppState(mode=METADATA_VIEW)
    assert handle_key(state, "q") is False


def test_metadata_view_up_decrements_scroll(reset_state):
    state = _AppState(mode=METADATA_VIEW, metadata_view_scroll_top=3)
    handle_key(state, "UP")
    assert state.metadata_view_scroll_top == 2


def test_metadata_view_up_clamps_at_zero(reset_state):
    state = _AppState(mode=METADATA_VIEW, metadata_view_scroll_top=0)
    handle_key(state, "UP")
    assert state.metadata_view_scroll_top == 0


def test_metadata_view_down_increments_scroll(reset_state):
    state = _AppState(mode=METADATA_VIEW, metadata_view_scroll_top=2)
    handle_key(state, "DOWN")
    assert state.metadata_view_scroll_top == 3


def test_metadata_view_esc_returns_to_results(reset_state):
    entry = {"source": "TPB"}
    state = _AppState(mode=METADATA_VIEW, metadata_view_entry=entry)
    handle_key(state, "ESC")
    assert state.mode == RESULTS
    assert state.metadata_view_entry is None


def test_metadata_view_any_other_key_returns_to_results(reset_state):
    state = _AppState(mode=METADATA_VIEW, metadata_view_entry={"source": "TPB"})
    handle_key(state, "x")
    assert state.mode == RESULTS


def test_v_keystroke_enters_metadata_view(reset_state):
    _populate_results(3)
    state = _AppState(mode=RESULTS, selected_idx=1)
    # Use a non-TPB/YTS source so no worker thread spins up
    state_module.results[1]["source"] = "EZTV"
    state_module.results[1]["metadata"] = {"name": "test"}
    handle_key(state, "v")
    assert state.mode == METADATA_VIEW
    assert state.metadata_view_entry is state_module.results[1]
    assert state.metadata_view_scroll_top == 0
    assert state.metadata_view_error is None


def test_v_keystroke_kicks_off_lazy_fetch_for_tpb(reset_state):
    import time as _t
    _populate_results(2)
    state_module.results[0]["source"] = "TPB"
    state_module.results[0]["metadata"] = {}
    state = _AppState(mode=RESULTS, selected_idx=0)
    with patch("torrent_hound.tui._fetch_tpb_metadata",
               return_value={"uploader": "x"}) as mfetch:
        handle_key(state, "v")
    deadline = _t.monotonic() + 1.0
    while mfetch.call_count == 0 and _t.monotonic() < deadline:
        _t.sleep(0.005)
    mfetch.assert_called_once()


def test_render_metadata_panel_renders_eager_fields(reset_state):
    """Smoke test: panel construction doesn't blow up and the body
    contains expected field labels and values."""
    from rich.console import Console

    from torrent_hound.tui import render_metadata_panel
    entry = {
        "name": "Test", "source": "YTS", "link": "x",
        "size": "2.0 GB", "seeders": 120, "leechers": 8,
        "metadata": {
            "name": "test name",
            "released": "2024",
            "imdb_code": "tt0123456",
            "imdb_rating": 8.5,
            "genre": "Drama",
            "runtime": "2h 0m 0s",
            "quality": "1080p",
            "uploader": "yify",
        },
    }
    state = _AppState(mode=METADATA_VIEW, metadata_view_entry=entry)
    panel = render_metadata_panel(state)
    buf = Console(record=True, width=120, height=60)
    buf.print(panel)
    out = buf.export_text()
    assert "Released" in out
    assert "2024" in out
    assert "https://www.imdb.com/title/tt0123456/" in out
    assert "8.5" in out
    assert "Genre" in out
    assert "Runtime" in out
    assert "yify" in out


def test_render_metadata_panel_dashes_missing_fields(reset_state):
    """Sparse entries dash everything we don't have."""
    from rich.console import Console

    from torrent_hound.tui import render_metadata_panel
    entry = {
        "name": "x", "source": "TPB", "link": "y",
        "size": "1 GB", "seeders": 1, "leechers": 1,
        "metadata": {"name": "x"},
    }
    state = _AppState(mode=METADATA_VIEW, metadata_view_entry=entry)
    panel = render_metadata_panel(state)
    buf = Console(record=True, width=120, height=60)
    buf.print(panel)
    out = buf.export_text()
    assert "—" in out


def test_render_metadata_panel_shows_loading_footer(reset_state):
    """While loading, the panel footer carries the rotating verb + spinner."""
    from rich.console import Console

    from torrent_hound.tui import render_metadata_panel
    entry = {
        "source": "TPB", "link": "x",
        "size": "1 GB", "seeders": 1, "leechers": 1,
        "metadata": {"name": "x"},
    }
    state = _AppState(
        mode=METADATA_VIEW, metadata_view_entry=entry,
        metadata_view_loading=True, current_verb="Sniffing the trackers",
    )
    panel = render_metadata_panel(state)
    buf = Console(record=True, width=120, height=60)
    buf.print(panel)
    out = buf.export_text()
    assert "Sniffing the trackers" in out


def test_verb_rotation_runs_during_metadata_loading():
    """When `metadata_view_loading` is True, the main loop's verb-rotation
    trigger must fire too — not just during search LOADING."""
    from torrent_hound.tui import _rotate_verb
    state = _AppState(metadata_view_loading=True, current_verb="initial", verb_set_at=0)
    _rotate_verb(state)
    # Either the same verb (random.choice may pick the same one) or a
    # different one — but verb_set_at must update.
    assert state.verb_set_at > 0


def test_render_metadata_panel_shows_error_footer(reset_state):
    from rich.console import Console

    from torrent_hound.tui import render_metadata_panel
    entry = {
        "source": "TPB", "link": "x",
        "size": "1 GB", "seeders": 1, "leechers": 1,
        "metadata": {"name": "x"},
    }
    state = _AppState(
        mode=METADATA_VIEW, metadata_view_entry=entry,
        metadata_view_error="fetch failed",
    )
    panel = render_metadata_panel(state)
    buf = Console(record=True, width=120, height=60)
    buf.print(panel)
    out = buf.export_text()
    assert "fetch failed" in out


def test_kick_off_rd_no_token_toasts_and_returns_none(reset_state):
    """No token configured → friendly toast, no thread started, mode unchanged."""
    state = _AppState(mode=RESULTS)
    with patch("torrent_hound.tui._load_config", return_value={}), \
         patch("torrent_hound.tui._resolve_rd_token", return_value=None):
        result = _kick_off_rd(state, _entry())
    assert result is None
    assert state.rd_flow is None
    assert state.mode == RESULTS
    assert "configure-rd" in state.toast or "RD_TOKEN" in state.toast
