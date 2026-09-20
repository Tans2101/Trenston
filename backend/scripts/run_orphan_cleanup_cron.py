"""POST /api/admin/cleanup-orphaned-documents for the Render cron job (stdlib only).

Uses SETUP_SECRET (X-Setup-Secret) — the admin cleanup route is gated by
_require_setup_secret, not INTERNAL_CRON_SECRET.
"""
from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request

URL = (os.environ.get("ORPHAN_CLEANUP_CRON_URL") or "").strip()
SECRET = (os.environ.get("SETUP_SECRET") or "").strip()


def main() -> int:
    if not URL:
        print("ORPHAN_CLEANUP_CRON_URL is not set", file=sys.stderr)
        return 1
    if not SECRET:
        print("SETUP_SECRET is not set", file=sys.stderr)
        return 1
    req = urllib.request.Request(
        URL,
        data=b"{}",
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Setup-Secret": SECRET,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            print(body)
            return 0 if 200 <= resp.status < 300 else 1
    except urllib.error.HTTPError as exc:
        print(exc.read().decode("utf-8", errors="replace"), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
