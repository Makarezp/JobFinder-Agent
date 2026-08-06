"""Make the tool importable to its own tests.

The tests live beside the tool rather than in the project's ``tests/`` tree so
that the whole directory can be lifted into its own repository unchanged. The
directory name contains a hyphen, so it is not importable as a package -- but
putting it on ``sys.path`` makes the plain module import work, which is simpler
and more robust than reconstructing the module from a spec.
"""

from __future__ import annotations

import sys
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parents[1]

if str(TOOL_DIR) not in sys.path:
    sys.path.insert(0, str(TOOL_DIR))
