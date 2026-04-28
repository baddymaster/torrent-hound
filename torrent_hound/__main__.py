"""Entry point for `python -m torrent_hound` and the PyInstaller binary build.

Absolute import (rather than `from . import main`) is intentional — PyInstaller
runs this file as a top-level script, where relative imports have no parent
package and would fail. Absolute import works in both contexts because
`-m torrent_hound` puts the package on `sys.path` and PyInstaller bundles it."""
from torrent_hound import main

if __name__ == "__main__":
    main()
