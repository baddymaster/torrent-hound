"""Tests for the --json / --quiet scriptable-output serialiser."""


def test_public_view_strips_private_metadata_keys(th):
    """`_apibay_id`, `_yts_movie_id`, `_lazy_fetched`, `_lazy_fetching` are
    TUI-internal routing hints and must not appear in the scriptable
    output where downstream consumers might mistake them for stable API."""
    row = {
        "name": "x", "link": "y", "seeders": 1, "leechers": 1,
        "size": "1G", "ratio": "1.0", "magnet": "magnet:?",
        "metadata": {
            "name": "x",
            "released": "2024",
            "_apibay_id": "12345",
            "_yts_movie_id": 67890,
            "_lazy_fetched": True,
            "_lazy_fetching": False,
        },
    }
    out = th.ui._public_view(row)
    assert sorted(out["metadata"].keys()) == ["name", "released"]
    # public fields preserved unchanged
    assert out["name"] == "x"
    assert out["seeders"] == 1


def test_public_view_unchanged_when_no_private_keys(th):
    """When metadata has no private keys, the original dict must pass
    through (don't pay copy cost on the common path)."""
    row = {
        "name": "x", "link": "y", "seeders": 1, "leechers": 1,
        "size": "1G", "ratio": "1.0", "magnet": "magnet:?",
        "metadata": {"name": "x", "released": "2024"},
    }
    out = th.ui._public_view(row)
    assert out is row  # same identity, not a copy


def test_public_view_handles_no_metadata_field(th):
    """Some legacy rows might not have a metadata key at all — must not raise."""
    row = {"name": "x", "link": "y", "seeders": 1, "leechers": 1,
           "size": "1G", "ratio": "1.0", "magnet": "magnet:?"}
    out = th.ui._public_view(row)
    assert out is row


def test_convert_to_json_filters_private_keys_from_apibay_rows(th):
    """End-to-end through `convertListJSONToPureJSON`: a TPB row carrying
    `_apibay_id` must NOT carry it after serialisation."""
    rows = [
        {
            "name": "Some Movie", "link": "https://thepiratebay.org/torrent/1/",
            "seeders": 100, "leechers": 5, "size": "2 GB", "ratio": "20.0",
            "magnet": "magnet:?xt=urn:btih:abcd",
            "metadata": {
                "name": "Some Movie", "released": "2024",
                "_apibay_id": "12345",  # must be filtered
            },
        },
    ]
    out = th.convertListJSONToPureJSON(rows)
    assert out["count"] == "1"
    serialised = out["results"]["0"]
    assert "_apibay_id" not in serialised["metadata"]
    assert serialised["metadata"]["released"] == "2024"


def test_convert_to_json_filters_private_keys_from_yts_rows(th):
    """Same protection for YTS's `_yts_movie_id` key, which has been
    leaking into --json output for longer than apibay's analog."""
    rows = [
        {
            "name": "Some Movie [1080p]", "link": "https://yts.bz/movies/x",
            "seeders": 50, "leechers": 2, "size": "1.8 GB", "ratio": "25.0",
            "magnet": "magnet:?xt=urn:btih:efgh",
            "metadata": {
                "name": "Some Movie [1080p]",
                "released": "2024",
                "_yts_movie_id": 67890,
            },
        },
    ]
    out = th.convertListJSONToPureJSON(rows)
    serialised = out["results"]["0"]
    assert "_yts_movie_id" not in serialised["metadata"]


def test_convert_to_json_does_not_mutate_input(th):
    """The serialiser must not mutate the source row's metadata — that
    dict is also referenced by the in-memory cache and the TUI's metadata
    overlay, both of which need the private keys."""
    md = {"name": "x", "_apibay_id": "12345"}
    row = {
        "name": "x", "link": "y", "seeders": 1, "leechers": 1,
        "size": "1G", "ratio": "1.0", "magnet": "magnet:?",
        "metadata": md,
    }
    th.convertListJSONToPureJSON([row])
    # Original metadata dict must still carry the private key
    assert "_apibay_id" in md
