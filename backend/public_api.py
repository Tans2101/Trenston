"""Stable, compact shapes for the read-only public API (/api/v1).

The v1 endpoints call the same handlers the app uses (so every permission and
plan rule still applies) and then pass the result through these projections.
Projections are allow-lists: a field only reaches an outside tool if it is
named here. That keeps the public contract small and stops app-only data (for
example a user's Gmail snippets on the Briefing) from leaking to agents.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

API_VERSION = "v1"


def _pick(src: Optional[dict], keys: Iterable[str]) -> dict:
    src = src or {}
    return {k: src.get(k) for k in keys}


def _rows(items, keys: Iterable[str]) -> list[dict]:
    keys = tuple(keys)
    return [_pick(i, keys) for i in (items or []) if isinstance(i, dict)]


def me(principal: dict, workspace: dict, *, financials_access: bool) -> dict:
    return {
        "api_version": API_VERSION,
        "user": {"name": principal.get("name"), "email": principal.get("email")},
        "workspace": {
            "id": workspace.get("workspace_id"),
            "name": workspace.get("name"),
            "currency": workspace.get("currency"),
            "timezone": workspace.get("timezone"),
        },
        "role": principal.get("role"),
        "access": {"financials": bool(financials_access)},
        "read_only": True,
    }


BRIEFING_METRIC_KEYS = ("label", "value", "delta", "tone", "section")
BRIEFING_CHANGE_KEYS = ("title", "detail", "tone")
BRIEFING_DECIDE_KEYS = ("id", "title", "detail", "urgency")
BRIEFING_DELEGATE_KEYS = ("title", "owner", "detail")
BRIEFING_UPDATE_KEYS = ("user_name", "text", "blocker", "ago")


def briefing(payload: dict) -> dict:
    """Briefing without per-user mailbox data (email_threads, Gmail flags)."""
    return {
        "date": payload.get("date"),
        "headline": payload.get("headline"),
        "summary": payload.get("ai_summary"),
        "metrics": _rows(payload.get("metrics"), BRIEFING_METRIC_KEYS),
        "what_changed": _rows(payload.get("what_changed"), BRIEFING_CHANGE_KEYS),
        "what_to_decide": _rows(payload.get("what_to_decide"), BRIEFING_DECIDE_KEYS),
        "what_to_decide_total": payload.get("what_to_decide_total"),
        "what_to_delegate": _rows(payload.get("what_to_delegate"), BRIEFING_DELEGATE_KEYS),
        "team_updates": _rows(payload.get("team_updates"), BRIEFING_UPDATE_KEYS),
        "data_as_of": payload.get("data_as_of"),
    }


DECISION_KEYS = (
    "id", "title", "category", "description", "recommendation", "confidence",
    "status", "impact", "due", "owner",
)


def decisions(payload: dict) -> dict:
    return {
        "decisions": _rows(payload.get("decisions"), DECISION_KEYS),
        # Drafted by Trenston from live signals; nothing here is decided until a person confirms it.
        "suggestions": _rows(payload.get("suggestions"), DECISION_KEYS),
    }


TASK_KEYS = ("id", "title", "assignee", "priority", "tag", "due", "overdue", "progress")


def tasks(payload: dict) -> dict:
    names = {c.get("id"): c.get("name") for c in (payload.get("columns") or []) if isinstance(c, dict)}
    out = []
    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        row = _pick(item, TASK_KEYS)
        row["status"] = names.get(item.get("column"), item.get("column"))
        row["done"] = item.get("column") == "done"
        out.append(row)
    return {"tasks": out}


WORK_ITEM_KEYS = (
    "id", "title", "department_name", "department_type", "status", "due_date",
    "overdue", "relationship",
)


def my_work(payload: dict) -> dict:
    return {"items": _rows(payload.get("items"), WORK_ITEM_KEYS)}


def _figure(display: Any, state: Optional[str], value: Any) -> dict:
    """Never report a figure that was not entered as zero."""
    entered = state not in (None, "not_entered")
    return {
        "display": display if entered else None,
        "value": value if entered else None,
        "state": state or "not_entered",
    }


def financials(fin: dict) -> dict:
    return {
        "currency": fin.get("currency"),
        "latest_month": fin.get("latest_month"),
        "mrr": _figure(fin.get("mrr"), fin.get("mrr_state"), fin.get("mrr_value")),
        "arr": _figure(fin.get("arr"), fin.get("mrr_state"), None),
        "burn": _figure(fin.get("burn"), fin.get("burn_state"), fin.get("burn_value")),
        "cash": _figure(fin.get("cash"), fin.get("cash_state"), fin.get("cash_value")),
        "runway_months": fin.get("runway_months"),
        "runway_state": fin.get("runway_state"),
        "gross_margin": fin.get("gross_margin") if fin.get("gross_margin") not in (None, "—") else None,
        "monthly": [
            {"month": m.get("month"), "revenue": m.get("revenue"), "expenses": m.get("expenses")}
            for m in (fin.get("ledger_months") or [])
            if isinstance(m, dict)
        ],
        "note": (
            "Figures with state 'not_entered' have not been added to Trenston yet. "
            "They are not zero."
        ),
    }
