# Changelog

All notable changes to Torrent Hound are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [3.0.2] - 2026-04-28

- Documenting EZTV empty-vs-failed fix in CHANGELOG for v3.0.2
- Distinguishing EZTV empty results (torrents_count==0) from mirror failure

### Fixed

- **EZTV no longer reports "all mirrors failed" for queries that resolve to
  an IMDB ID with zero EZTV torrents** (e.g. `kung fu panda` — IMDB has the
  TV show but EZTV doesn't host any episodes for it). The API responds
  successfully with `torrents_count: 0`; we now classify that as `empty` and
  stop probing instead of walking all four mirrors and emitting `failed`.
  Same class of bug as the TPB and YTS fixes shipped in v3.0.0; this final
  case slipped through because EZTV's existing `empty` path only covered
  the no-IMDB-match scenario.

## [3.0.1] - 2026-04-28

### Fixed

- **Standalone binary build.** The `Release` workflow was still pointing
  at `torrent_hound.py` (the pre-package-split monolith). v3.0.0
  published cleanly to PyPI but the corresponding GitHub Release with
  PyInstaller binaries for Linux/macOS/Windows failed to build. The
  workflow now targets `torrent_hound/__main__.py`; v3.0.1 ships
  identical Python code with a working binary release.

## [3.0.0] - 2026-04-28

### Added

- **Single-screen TUI** built on `rich.live` replaces the old REPL `Enter
  command :` loop. Arrow-key navigation, mode-aware footer, live filter,
  inline Real-Debrid handoff. Quiet/JSON modes (`--quiet`, `--json`)
  bypass the TUI entirely.
- **Per-source fetch trail.** Three-row header:
  - top: rotating verb spinner (during fetch) → run summary (after)
  - middle: `trail:` line — per-source pip with mirror retry detail and
    inline timing (`TPB ✓ 10 (180ms) · YTS ✓ 8 (420ms · 1 retry) · EZTV
    ⚡ 5 cached 3m`)
  - bottom: `selected: <source> · <name>` of the highlighted row
- **Multi-character commands** via vim-style chord buffer:
  - `c` (alone) copy magnet · `cs` copy + open Seedr
  - `r` (alone) repeat search · `rd` send to Real-Debrid
  - When a chord prefix is pending, the footer shows the available
    extensions so the chord-timeout window feels like a menu rather than
    a freeze.
- **In-app new search.** `s` enters a new-query prompt; `r` repeats the
  current search. No more quitting and re-running.
- **Live filter.** `/` enters filter mode. Type to narrow; arrows still
  navigate the filtered subset; `⏎` accepts; `Esc` clears.
- **Live source-progress callbacks.** `searchAllSites(progress_callback=...)`
  surfaces per-mirror events (`mirror_attempt` / `mirror_failed` / `ok`
  / `cached` / `failed`) for the TUI's trail.
- **TUI unit tests.** `tests/test_tui.py` covers `read_key` (all four
  arrow keys, bare ESC, Alt-letter, unknown CSI) and `handle_key` state
  transitions across all modes (RESULTS / FILTER / SEARCH / LOADING)
  including chord buffering and ESC cancellation.

### Changed

- **Package layout.** `torrent_hound.py` split into a proper `torrent_hound/`
  package (`cli`, `tui`, `state`, `cache`, `config`, `realdebrid`, `ui`,
  `sources/`). No behaviour change beyond the TUI rewrite; cleaner
  foundation for future work.
- **Shell completion** setup now uses `torrent-hound --print-completion
  {bash,zsh}` instead of `register-python-argcomplete torrent-hound`.
  The latter ships inside the argcomplete dependency and isn't exposed
  on PATH when installed via pipx.
- **YTS mirror list refresh.** Added `yts.bz` and `yts.gg` (both
  confirmed official — their JSON responses embed an operator-signed
  migration notice pointing to `https://movies-api.accel.li/api/v2/`,
  corroborated by the yts.bz API documentation page). Removed `yts.mx`
  (DNS no longer resolves) and `yts.rs` (Cloudflare 523 origin
  unreachable).

### Removed

- **REPL.** The interactive `Enter command :` loop (and `repl.py`) are
  gone. Quiet/JSON output paths are unchanged.
- **Numeric command prefixes.** `c1`, `m2`, `rd3` etc. no longer exist;
  the TUI's cursor selects the row and the bare command acts on it.
- **Python 3.9 support.** Minimum supported Python is 3.10.

### Fixed

- **Sources no longer report "all mirrors failed" for genuine empty
  results.** Both TPB and YTS were probing every mirror in the chain
  when the upstream API worked but returned zero matches, then emitting
  `✗ all mirrors failed` in the trail and a corresponding toast. Now
  they emit a clean `no results` event after the first responsive
  mirror — TPB via a structural check on the search-results table
  (header-only-row signals a successful empty page versus a missing
  table that signals a dead mirror), YTS via gating on the `movies`
  array being non-empty (catches both pure-zero queries and the
  quirkier `movie_count > 0 + missing movies key` shape that e.g.
  wrong-year queries produce).
- **YTS inline quality tokens** like `1080p`, `720p`, `2160p`,
  `1080p.x265`, and `3D` appended to a search query no longer silently
  return zero. YTS's `query_term` does title-only substring matching,
  so quality tokens never matched a movie title. We now extract them
  via `_extract_yts_quality` and route them to YTS's dedicated
  `?quality=` API parameter, then post-filter the returned torrent
  variants so the user sees only the requested quality.
- **YTS movie-page links** now use the post-redirect host. A request
  to `yts.lt` that 301'd to `yts.bz` was rewriting links with the
  originally-requested host (a dead mirror); now they use the actual
  responding host from `r.url`.
- **Per-source spinner in the trail line** now animates. The in-flight
  glyph was a static `⠋`; it now rotates through the standard 10-frame
  dots pattern based on monotonic time.

### Migration notes

- Anyone scripting against `--quiet` / `--json` is unaffected — those
  paths bypass the TUI.
- Anyone embedding the package (`import torrent_hound`) keeps the same
  re-export surface; new modules (`tui`, etc.) sit alongside the existing
  names.
- `from torrent_hound.repl import switch` etc. — `repl.py` is gone. The
  TUI's per-key handlers live in `torrent_hound.tui`.

## [2.6.2] - 2026-04-18

- Reordering imports so ruff isort check passes

## [2.6.1] - 2026-04-18

### Changed
- Shell completion setup now uses `torrent-hound --print-completion {bash,zsh}`
  instead of `register-python-argcomplete torrent-hound`. The latter ships
  inside the argcomplete dependency and isn't exposed on PATH when installed
  via pipx, forcing users to `pipx inject` argcomplete separately. Routing
  the snippet through torrent-hound's own CLI sidesteps that entirely.

## [2.6.0] - 2026-04-17

- Updating README and CHANGELOG for new r semantics
- Making r REPL command cache-aware (cached sources reused, failed sources retry)
- Mentioning cache behavior in h command help menu for s and r
- Making r REPL command actually bypass the cache as documented
- Making s REPL command cache-aware instead of always bypassing
- Documenting result cache in README and CHANGELOG
- Wiring result cache into searchAllSites with mixed-hit feedback
- Adding result-cache module state and helpers (get, put, format-age, normalize)
- Listing argcomplete in README runtime dependencies
- Clarifying zsh compinit precondition in completion docs
- Documenting shell completion in README and CHANGELOG
- Wiring argcomplete into main() for top-level CLI flag completion
- Extracting _build_ parser helper to isolate parser construction from main()
- Adding argcomplete>=3.0 as a runtime dependency
- Tidying 2.5.0 changelog

### Added
- Shell completion for top-level CLI flags via `argcomplete`. Enable by
  adding a small snippet to `~/.bashrc` or `~/.zshrc` — see the README's
  "Shell completion" section for the exact commands per shell.
- In-memory per-session result cache (5-min TTL, keyed by normalized
  query + source). Repeat queries within a session return instantly;
  `r` retries any sources that previously errored while reusing cached
  ones. Re-launch the CLI to force a fresh fetch of all sources.

## [2.5.0] - 2026-04-17

### Added
- Real-Debrid integration via `rd<n>` command — submits the selected torrent to RD, waits for hoster links, and dispatches to a configurable action
- Four action modes: `clipboard` (default), `print`, `browser`, `downie` (via `downie://XUL/?url=` URL scheme on macOS)
- Interactive multi-file picker for season packs and multi-part torrents
- TOML config file at `~/Library/Application Support/torrent-hound/config.toml` (macOS) / `~/.config/torrent-hound/config.toml` (Linux) / `%APPDATA%\torrent-hound\config.toml` (Windows) — first time the project has one
- `RD_TOKEN` env var support for ad-hoc use without saving anything to disk
- `--configure-rd` CLI flag for one-step interactive token + action setup (getpass hidden entry; stdin-pipe supported for scripting)
- `--config-path` CLI flag — prints the resolved config file path
- `--user-status` CLI flag — prints account type, premium expiration, and points via `GET /user`
- `--revoke-rd-token` CLI flag — invalidates the current token via `GET /disable_access_token`, optionally wipes it from config
- RD error classification surfaces documented `error_code` values (8, 9, 14, 20, 21, 22, 23, 34, 37) with specific user-facing messages per code; generic fallback includes body context for unrecognised codes
- Graceful degradation when RD disables the undocumented `/torrents/instantAvailability` endpoint for an account (error_code 37 or 3 are swallowed; `rd<n>` converges through the submit + unrestrict flow)
- Already-selected detection on re-runs (skips redundant `selectFiles` after RD returns 202 "Action already done")
- Single 60-second retry on HTTP 429 rate-limit responses (per RD docs, no multi-retry to avoid extending the block duration)
- `config.toml` added to `.gitignore` so tokens can't accidentally land in git history

### Security
- Config file written with `0600` permissions and parent directory with `0700` (re-applied on overwrite to harden any pre-existing loose modes)
- URL-scheme allowlist on direct links from RD before `webbrowser.open()` / Downie dispatch — only `https://` is accepted; `file://`, `javascript:`, `tel:`, and custom schemes are filtered out as defence against a hostile or MITM'd RD response
- ANSI escape stripping on torrent names and filenames in the file picker to prevent terminal-UI spoofing from malicious torrent metadata
- Unicode decimal digits rejected in the picker's selection parser (ASCII-only enforcement)
- Token never echoed by `--configure-rd` or confirmation messages; 401 error no longer leaks `$HOME` path

### Fixed
- `nargs='*'` on the query argument no longer iterates the string default when no args are given
- HTTP 202 from `selectFiles` treated as idempotent success (fixes misleading "captive portal" error on re-runs)
- HTTP 201 from `addMagnet` recognised as success (was erroneously tripping the generic error path in early prototypes)
- `_cmd_rd` catches `KeyError`/`TypeError` from unexpected RD response shapes instead of crashing the REPL
- `_rd_request` catches `ValueError` on non-JSON 200 responses (captive portals) and surfaces a friendly message
- `_load_config` catches `UnicodeDecodeError` on non-UTF-8 config files

### Dependencies
- Added `platformdirs>=4.0` (cross-platform config directory resolution)
- Added `tomli>=2.0; python_version<'3.11'` (TOML reader backport; stdlib `tomllib` covers 3.11+)
- Added `tomli_w>=1.0` (TOML writer for `--configure-rd`; stdlib `tomllib` is read-only)

## [2.4.2] - 2026-04-16

- Updating README
- Adding sources table to README
- Bumping upload/download-artifact to v6

## [2.4.1] - 2026-04-16

- Adding tests for EZTV slugs, u command URLs, TPB link domains, and Unicode stripping
- Showing all source URLs in the u command
- Fixing EZTV links to include slug for valid torrent page URLs
- Fixing table alignment by stripping wide Unicode chars from torrent names
- Fixing table layout to keep numeric columns visible at narrow terminal widths

### Changed
- `u` command now shows URLs for all active sources (TPB, YTS, EZTV), not just TPB

### Fixed
- EZTV links now include the slug for valid torrent page URLs
- TPB links now use the working mirror domain instead of relative paths
- YTS links now use the working mirror domain instead of whatever the API returned
- Table alignment no longer broken by emoji / wide Unicode characters in torrent names

## [2.4.0] - 2026-04-16

### Added
- YTS as a torrent source (movies, JSON API, no Cloudflare, fallback domain chain)
- EZTV as a torrent source (TV shows via IMDB lookup, episode/quality/keyword filtering, fallback domain chain)
- Quality tags in YTS results (`[720p]`, `[1080p]`, `[2160p]`)
- 34 new tests (56 total): YTS parser, EZTV parser, episode query parsing, IMDB bridge, domain fallback

## [2.3.1] - 2026-04-16

### Changed
- Version now derived from git tags via `setuptools-scm` (no manual version bumps needed)
- Removed lockfile from CI (incompatible with multi-Python matrix)

## [2.3.0] - 2026-04-16

### Added
- Standalone binary release workflow (PyInstaller builds for Linux, macOS, Windows on every version tag)
- `requirements.lock` for reproducible CI/dev builds (generated via pip-compile)
- Automated PyPI publishing via Trusted Publisher

### Changed
- Dependency version floors tightened to tested versions (beautifulsoup4>=4.12, requests>=2.28, pyperclip>=1.8, rich>=13.0)
- CI now installs from lockfile before editable install
- GitHub Actions bumped to Node 24 (checkout@v6, setup-python@v6)

## [2.2.2] - 2026-04-16

### Fixed
- Empty project description on PyPI (added `readme = "README.md"` to pyproject.toml)
- GitHub Actions Node 20 deprecation warnings (bumped to actions/checkout@v6, actions/setup-python@v6)

## [2.2.1] - 2026-04-16

### Added
- Automated PyPI publishing via GitHub Actions (Trusted Publisher, triggers on version tags)

## [2.2.0] - 2026-04-15

### Added
- `--json` flag for scriptable, pipeline-friendly output
- `--version` / `-V` flag
- TPB fallback domain chain (5 mirrors, auto-remembers the working one)
- Parallel source fetching via `ThreadPoolExecutor` (ready for multi-source)
- Pytest test suite (22 tests covering parser, switch dispatcher, fallback chain)
- `ruff` linter config + GitHub Actions CI (pytest matrix across Python 3.9-3.13)
- README badges (CI, PyPI, Python versions, license)
- `pyproject.toml` for modern Python packaging and `pip install` support
- Cloudflare captcha detection in 1337x search (one-line error message)

### Changed
- `switch()` rewritten with regex dispatch and a single `_get_entry()` helper (was ~200 lines of copy-paste, now ~50)
- `clint` + `VeryPrettyTable` replaced with `rich` for table rendering (+ minimal ANSI shim for inline colors)
- Source file renamed from `torrent-hound.py` to `torrent_hound.py` (enables proper Python packaging)
- Entry point extracted into `def main()` for `[project.scripts]` compatibility
- Help menu simplified (removed `p0`/`p1` toggle and stale `cz` zbigz command)
- `-q` quiet mode now suppresses "Searching..." progress output
- README fully rewritten for current state (pipx install, scripting mode, troubleshooting, disclaimer)
- Copyright updated to 2017-2026

### Removed
- RARBG source (shut down in 2023)
- SkyTorrents source (defunct)
- 1337x search disabled (Cloudflare managed challenge; code kept for future re-enablement)
- Legacy TPB parser (`searchPirateBay`, `_parse_search_result_table`, `_parse_search_result_table_row`)
- TPB API path (`searchPirateBayWithAPI`, `parse_results_tpb_api`)
- All RARBG functions (~180 lines)
- All SkyTorrents functions (~120 lines)
- Python 2 compatibility shims (`from __future__`, `from builtins`)
- Unused dependencies: `clint`, `VeryPrettyTable`, `humanize`, `cfscrape`
- `bin/torrent-hound` (stale copy of source file, not a real binary)
- `requirements.txt` / `requirements-dev.txt` (replaced by `pyproject.toml`)
- `ruff.toml` (consolidated into `pyproject.toml`)

### Fixed
- Quiet mode (`-q`) was reading `results_tpb_api` instead of `results_tpb_condensed`, reporting 0 TPB results
- `u` command labelled 1337x URL as "SkyTorrents"
- BS4 `findAll` deprecation warnings (renamed to `find_all`)
- Copyright start year corrected to 2017 (project's first commit)

## [1.5] - 2018-04-01

See [git history](https://github.com/baddymaster/torrent-hound/commits/v1.5) for details.

## [1.0] - 2017-03-24

Initial release.
