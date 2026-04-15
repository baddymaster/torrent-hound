# Torrent Hound

A terminal-first torrent search CLI. Type a query, get ranked results from
multiple trackers in one table, then copy a magnet link or open the torrent
page with a single keystroke.

```
$ torrent-hound ubuntu
                                          PirateBay
┏━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━┳━━━━┳━━━━━━┓
┃ No ┃ Torrent Name                                         ┃      Size ┃  S ┃  L ┃  S/L ┃
┡━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━╇━━━━╇━━━━━━┩
│ 1  │ ubuntu-24.04.1-desktop-amd64.iso                     │  5.78 GiB │ 40 │  2 │ 20.0 │
│ 2  │ Ubuntu 22.04 LTS                                     │   3.4 GiB │ 32 │  1 │ 32.0 │
│ …  │                                                      │           │    │    │      │
└────┴──────────────────────────────────────────────────────┴───────────┴────┴────┴──────┘

Enter command : c1
Magnet link copied to clipboard!
```

## Requirements

- Python 3.9+
- Runtime dependencies: `beautifulsoup4`, `requests`, `pyperclip`, `rich`

## Install

### Via pipx (recommended)

[`pipx`](https://pipx.pypa.io/) installs each Python CLI into its own isolated
venv and automatically puts the entry point on your `$PATH`.

```
pipx install torrent-hound
```

If you don't already have pipx: `brew install pipx` (macOS), `sudo apt install pipx` (Ubuntu/Debian), or `python3 -m pip install --user pipx && python3 -m pipx ensurepath`.

### Via pip

```
pip install torrent-hound
```

Whether this lands `torrent-hound` on your `$PATH` depends on *where* pip
installed its scripts directory:

- **Inside an active venv**: always on PATH while the venv is active.
- **`pip install --user` (macOS / Linux)**: scripts go to `~/.local/bin`. Add it to PATH if missing:
    ```
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc   # or ~/.bashrc
    ```
    Reload your shell, or run `source ~/.zshrc`.
- **`pip install --user` (Windows)**: scripts go to `%APPDATA%\Python\PythonXX\Scripts`. Find the exact path with `python -m site --user-base`, then add that `Scripts` directory to PATH via **System Properties → Environment Variables**.
- **System-wide `sudo pip install`** (Linux/macOS): scripts go to `/usr/local/bin`, which is almost always on PATH. Modern Python distributions may refuse this install with a PEP 668 "externally-managed-environment" error — prefer pipx or a venv instead.

Upgrade later with `pip install -U torrent-hound` (or `pipx upgrade torrent-hound`).

### From source

```
git clone https://github.com/baddymaster/torrent-hound.git
cd torrent-hound

# Create a venv so deps don't pollute your system Python
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Then invoke it directly:

```
python3 torrent-hound.py <query>
```

Optionally symlink the script onto your `$PATH`:

```
ln -s "$(pwd)/torrent-hound.py" ~/.local/bin/torrent-hound
```

## Usage

### Interactive mode (default)

```
torrent-hound ubuntu
```

Results render as a table; enter a command at the prompt.

| Command  | Action                                                  |
|----------|---------------------------------------------------------|
| `m<n>`   | Print the magnet link for result `<n>`                  |
| `c<n>`   | Copy the magnet link to clipboard                       |
| `cs<n>`  | Copy the magnet and open Seedr.cc                       |
| `d<n>`   | Hand the magnet to your default torrent client          |
| `o<n>`   | Open the torrent page in your default browser           |
| `p`      | Re-print the results table                              |
| `s`      | Enter a new query and search again                      |
| `r`      | Repeat the last search                                  |
| `u`      | Show the source URLs used for the current results       |
| `h`      | Show the help menu                                      |
| `q`      | Quit                                                    |

### Scripting mode

Non-interactive output, parseable from a pipeline:

```
# Python-repr output (legacy, --quiet / -q):
torrent-hound -q ubuntu

# JSON output:
torrent-hound --json ubuntu | jq '.tpb.results["0"].magnet'
```

`--json` emits a single valid JSON document to stdout and exits.

## Development

### Running tests

```
pip install -r requirements-dev.txt
pytest tests/
```

The suite runs fully offline (no network calls) — it uses a captured fixture
HTML response for parser tests and mocks `requests.get` for the fallback-
chain tests.

### Project layout

```
torrent-hound.py      # single-file entry point
tests/                # pytest suite
  conftest.py         # loads torrent-hound.py as a module
  fixtures/           # saved HTML responses for offline parser tests
requirements.txt      # runtime deps
requirements-dev.txt  # runtime + pytest
```

## Troubleshooting

**SSL handshake errors**: see [these Stack Overflow answers](https://stackoverflow.com/questions/31649390/python-requests-ssl-handshake-failure) for common fixes.

**`[PirateBay] Error : All known mirrors returned no results or were unreachable`**: every TPB domain in the fallback chain is blocked or down. Add a known-working mirror to `TPB_DOMAINS` at the top of `torrent-hound.py`.

**Blocked by Cloudflare captcha**: some sources serve a CF challenge that requires a real browser.

## Disclaimer

This software is provided as-is, with no warranty of any kind. It is intended
for discovering legally-distributable content and is **not** intended to be used for downloading, distributing, or
facilitating access to copyrighted material without authorisation. You are
responsible for complying with the laws of your jurisdiction.

## License

AGPL-3.0 — see [LICENSE](LICENSE).
