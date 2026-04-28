"""Pytest bootstrap: expose the torrent_hound package under the name `th`."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
FIXTURES = Path(__file__).parent / "fixtures"

# Make the package importable without requiring an editable install.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Prevent argparse in main() from eating real CLI args during import
sys.argv = ["torrent-hound", "dummy"]

import torrent_hound as _torrent_hound  # noqa: E402


@pytest.fixture(scope="session")
def th():
    """The torrent_hound package, re-exporting names from the current
    migration state (monolith + extracted submodules)."""
    return _torrent_hound


@pytest.fixture
def tpb_ubuntu_html():
    """Real captured TPB search response for 'ubuntu'."""
    return (FIXTURES / "tpb_search_ubuntu.html").read_bytes()


@pytest.fixture
def tpb_no_hits_html():
    """Real captured TPB search response for a query with zero matches.
    The page renders the searchResult table with only its header row."""
    return (FIXTURES / "tpb_search_no_hits.html").read_bytes()


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
