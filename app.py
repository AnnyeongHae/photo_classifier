"""
Top-level entry point for both development and Nuitka-compiled exe.
"""
import sys
from pathlib import Path

# Ensure project root is on sys.path (needed for Nuitka standalone)
_ROOT = Path(__file__).parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from gui.app import run

if __name__ == "__main__":
    sys.exit(run())
