"""Pytest bootstrap: load torrent_hound.py as a module under the name `th`."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SOURCE = ROOT / "torrent_hound.py"
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


@pytest.fixture
def yts_interstellar_json():
    """Real captured YTS API response for 'interstellar'."""
    return json.loads((FIXTURES / "yts_search_interstellar.json").read_text())


@pytest.fixture
def eztv_severance_json():
    """Real captured EZTV API response for Severance (IMDB 11280740)."""
    return json.loads((FIXTURES / "eztv_search_severance.json").read_text())


@pytest.fixture
def imdb_suggestion_severance_json():
    """Real captured IMDB suggestion response for 'severance'."""
    return json.loads((FIXTURES / "imdb_suggestion_severance.json").read_text())
