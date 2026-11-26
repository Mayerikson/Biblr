#!/usr/bin/env python3
"""Ponto de entrada estável: python scripts/vbp.py <comando>."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vbp.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
