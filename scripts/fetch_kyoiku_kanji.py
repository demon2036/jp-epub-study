#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


# Backward-compatible entrypoint.
# The actual implementation lives in `jp/crawler/kyoiku.py`
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from jp.crawler.kyoiku import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

