#!/usr/bin/env python3
"""Compatibility entry point for the packaged Mac Local Harness CLI."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from mac_harness.cli import main

if __name__ == "__main__":
    main()
