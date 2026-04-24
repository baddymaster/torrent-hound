# PYTHON_ARGCOMPLETE_OK
"""torrent_hound — multi-source torrent search CLI.

Structural package split in progress. During the migration, `_monolith.py`
is compiled and exec()'d into this module's namespace, so every name
defined there lives in `torrent_hound.__dict__` directly. That gives us:

  - live binding for module-level state (tests can assign `th.exit = X`
    and functions see the change via their `global exit` declarations),
  - function `__globals__` pointing at this namespace,
  - no proxy class, no __getattr__ tricks.

Commits 2-6 extract code out of _monolith.py into siblings. Each step
shrinks _monolith.py and adds a sibling import above the exec() call.
Final commit drops _monolith.py entirely and this file becomes a normal
re-export surface.

See tasks/specs/2026-04-17-package-split-design.md.
"""
from pathlib import Path as _Path

_monolith_path = _Path(__file__).parent / "_monolith.py"
exec(compile(_monolith_path.read_text(), str(_monolith_path), "exec"))

del _monolith_path, _Path
