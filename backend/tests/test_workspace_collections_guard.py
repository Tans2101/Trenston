"""Every collection that stores workspace data must be exported and deleted with the workspace.

Workspace export and deletion both iterate server._WORKSPACE_COLLECTIONS. A new
collection that writes rows with a workspace_id but is missing from that tuple
would survive "delete my workspace" and be missing from the owner's data export.
This scans the backend source so the omission fails in CI instead of in production.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]

# Collections that are intentionally NOT purged by the generic workspace loop.
# Each one is handled explicitly in _delete_workspace_data / delete_account, or
# holds no tenant business data.
HANDLED_ELSEWHERE = {
    "workspaces",          # deleted explicitly (delete_one)
    "memberships",         # deleted explicitly
    "departments",         # deleted explicitly
    "department_members",  # deleted explicitly via department ids
    "user_google_tokens",  # deleted explicitly
    "referrals",           # deleted explicitly
    "users",               # account-level, not workspace data
    "user_sessions",       # account-level
    "clerk_events",        # webhook idempotency ids, no tenant content
    "paddle_events",       # webhook idempotency ids, no tenant content
    "email_suppressions",  # keyed by email address, not workspace
    "join_rate_events",    # rate limiter, keyed by user/ip
    "payment_transactions",  # present in tuple but written only by billing code
}


def _workspace_collections() -> set[str]:
    src = (BACKEND / "server.py").read_text()
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "_WORKSPACE_COLLECTIONS":
                    return {elt.value for elt in node.value.elts if isinstance(elt, ast.Constant)}
    raise AssertionError("_WORKSPACE_COLLECTIONS not found")


def _written_collections() -> set[str]:
    names: set[str] = set()
    pattern = re.compile(r"\bdb\.([a-z_]+)\.(?:insert_one|insert_many|update_one|update_many|replace_one)\b")
    for path in BACKEND.glob("*.py"):
        names |= set(pattern.findall(path.read_text()))
    return names


def test_nine_previously_missed_collections_are_covered():
    covered = _workspace_collections()
    for name in (
        "production_daily_logs", "maintenance_schedules", "maintenance_spares",
        "maintenance_costs", "maintenance_contracts", "sales_order_book",
        "sales_targets", "document_usage_periods", "seat_usage",
    ):
        assert name in covered, f"{name} would survive workspace deletion and be missing from export"


def test_every_written_collection_is_covered_or_explicitly_handled():
    covered = _workspace_collections()
    missing = sorted(_written_collections() - covered - HANDLED_ELSEWHERE)
    assert missing == [], (
        "Collections written by the backend but neither in _WORKSPACE_COLLECTIONS nor "
        f"handled explicitly: {missing}. Add them so export and deletion cover them."
    )
