"""
Top-level entry point for both development and Nuitka-compiled exe.
"""
# -*- coding: utf-8 -*-
import sys

from gui.app import run

if __name__ == "__main__":
    sys.exit(run())
