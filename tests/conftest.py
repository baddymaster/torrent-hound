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
def tpb_modern_layout_html():
    """Real captured TPB search response from a mirror serving the modern
    8-cell row layout (no detLink class, magnet/size/seed/leech/uploader
    each in their own td). Trimmed to ~12 rows for fixture size."""
    return (FIXTURES / "tpb_search_modern_layout.html").read_bytes()


@pytest.fixture
def apibay_ubuntu_json():
    """Real captured apibay.org/q.php response for 'ubuntu', trimmed to
    five items. Apibay is the JSON API the TPB front-end SPA fetches from."""
    return json.loads((FIXTURES / "apibay_search_ubuntu.json").read_text())


@pytest.fixture
def tpb_no_hits_html():
    """Real captured TPB search response for a query with zero matches.
    The page renders the searchResult table with only its header row."""
    return (FIXTURES / "tpb_search_no_hits.html").read_bytes()


@pytest.fixture
def tpb_detail_movie_html():
    """Captured, sanitised TPB detail-page HTML for a movie torrent.
    Used by lazy-fetch parser tests for the structured + description paths."""
    return (FIXTURES / "tpb_detail_movie.html").read_bytes()


@pytest.fixture
def tpb_detail_iso_html():
    """Captured TPB detail-page HTML for an ISO torrent — sparse description,
    tests the data-poor case."""
    return (FIXTURES / "tpb_detail_iso.html").read_bytes()


@pytest.fixture
def tpb_detail_r1_html():
    """TPB detail page using a multi-line `Directors\\n<names>\\n\\n` block
    plus a `Stars\\n<names>\\n\\n` block, with the plot as a bare paragraph
    (no `Plot:` label). Sanitised."""
    return (FIXTURES / "tpb_detail_R1.html").read_bytes()


@pytest.fixture
def tpb_detail_r2_html():
    """TPB detail page with slash-separated genres and a bare-paragraph plot
    after the IMDB URL line. Sanitised."""
    return (FIXTURES / "tpb_detail_R2.html").read_bytes()


@pytest.fixture
def tpb_detail_r3_html():
    """TPB detail page using bracketed labels (`[FRAME RATE]`,
    `[AUDIO STREAM 1]`, `[SUBTITLES]`, `[RUNTIME]`) with `1Hr 32Min`
    style runtime. Sanitised."""
    return (FIXTURES / "tpb_detail_R3.html").read_bytes()


@pytest.fixture
def tpb_detail_r8_html():
    """TPB detail page using aligned `Label : value` rows with nested
    Video/Audio sub-sections; runtime as `1 h 32 min`. Sanitised."""
    return (FIXTURES / "tpb_detail_R8.html").read_bytes()


@pytest.fixture
def yts_movie_details_json():
    """Captured, sanitised `movie_details.json?with_cast=true` response for
    a YTS movie. Used by the lazy-fetch parser tests."""
    return json.loads((FIXTURES / "yts_movie_details.json").read_text())


@pytest.fixture
def yts_interstellar_json():
    """Real captured YTS API response for 'interstellar'."""
    return json.loads((FIXTURES / "yts_search_interstellar.json").read_text())


@pytest.fixture
def eztv_severance_json():
    """Real captured EZTV API response for Severance (IMDB 11280740)."""
    return json.loads((FIXTURES / "eztv_search_severance.json").read_text())


@pytest.fixture
def eztv_no_hits_json():
    """Real captured EZTV API response for an IMDB ID EZTV doesn't host.
    API returns torrents_count: 0 with no `torrents` key — must be
    classified as empty, not failed."""
    return json.loads((FIXTURES / "eztv_search_no_hits.json").read_text())


@pytest.fixture
def imdb_suggestion_severance_json():
    """Real captured IMDB suggestion response for 'severance'."""
    return json.loads((FIXTURES / "imdb_suggestion_severance.json").read_text())
