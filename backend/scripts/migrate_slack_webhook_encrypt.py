#!/usr/bin/env python3
"""Superseded by scripts.migrate_encrypt_slack_webhooks (dry-run by default, --apply to write)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.migrate_encrypt_slack_webhooks import main  # noqa: E402

if __name__ == "__main__":
    main()
