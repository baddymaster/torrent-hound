# Changelog

All notable changes to Torrent Hound are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [2.4.0] - 2026-04-16

### Added
- YTS as a torrent source (movies, JSON API, no Cloudflare, fallback domain chain)
- EZTV as a torrent source (TV shows via IMDB lookup, episode/quality/keyword filtering, fallback domain chain)
- Quality tags in YTS results (`[720p]`, `[1080p]`, `[2160p]`)
- 34 new tests (56 total): YTS parser, EZTV parser, episode query parsing, IMDB bridge, domain fallback

### Fixed
- TPB links now use the working mirror domain instead of relative paths
- YTS links now use the working mirror domain instead of whatever the API returned

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
