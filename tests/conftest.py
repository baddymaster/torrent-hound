"""Pytest bootstrap: load torrent-hound.py as a module under the name `th`.

The source file uses a hyphen in its name (`torrent-hound.py`), which isn't
importable via a normal `import` statement. We load it manually with
importlib and expose it as the fixture `th` so tests can do `th.function(...)`.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SOURCE = ROOT / "torrent-hound.py"
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def th():
    """Load the torrent-hound script as a module once per test session."""
    spec = importlib.util.spec_from_file_location("torrent_hound", SOURCE)
    module = importlib.util.module_from_spec(spec)
    # Prevent the __main__ block from running during import
    sys.argv = ["torrent-hound", "dummy"]
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def tpb_ubuntu_html():
    """Real captured TPB search response for 'ubuntu'."""
    return (FIXTURES / "tpb_search_ubuntu.html").read_bytes()
