"""Canonical section IDs for Team & Access → Manage Access grants."""

from __future__ import annotations

from typing import Any


DEFAULT_DEPARTMENTS: list[str] = [
    "Engineering",
    "Product",
    "Sales",
    "Marketing",
    "Finance",
    "Operations",
    "Support",
    "HR",
    "Growth",
    "General",
]

# Sections CEOs can grant beyond pack permissions (pack unlocks still apply separately).
MANAGEABLE_SECTIONS: list[dict[str, str]] = [
    {
        "id": "financials",
        "label": "Financials",
        "perm": "finance:write",
        "description": "Revenue, expenses, runway, and document uploads.",
    },
    {
        "id": "people",
        "label": "People",
        "perm": "people:write",
        "description": "Team roster and headcount.",
    },
    {
        "id": "sales",
        "label": "Pipeline",
        "perm": "sales:write",
        "description": "Deals, stages, and pipeline value.",
    },
    {
        "id": "reports",
        "label": "Reports",
        "perm": "reports:write",
        "description": "Manual reports and CEO Pack inputs.",
    },
    {
        "id": "tasks",
        "label": "Tasks",
        "perm": "tasks:assign",
        "description": "Create tasks and assign work to teammates.",
    },
    {
        "id": "decisions",
        "label": "Decisions",
        "perm": "decisions:act",
        "description": "Approve, delegate, or reject decision cards.",
    },
    {
        "id": "telemetry",
        "label": "Metrics",
        "perm": "telemetry:write",
        "description": "KPI notes, risk radar, and manual metric inputs.",
    },
    {
        "id": "calendar",
        "label": "Calendar",
        "perm": "calendar:write",
        "description": "Add, edit, and delete shared Trenston calendar events.",
    },
]


MANAGEABLE_SECTION_IDS = frozenset(item["id"] for item in MANAGEABLE_SECTIONS)
_SECTION_PERM = {item["id"]: item["perm"] for item in MANAGEABLE_SECTIONS}


def section_pack_perm(section_id: str) -> str:
    return _SECTION_PERM.get(section_id, "")


def normalize_section_access(raw: Any) -> dict[str, list[str]]:
    """Normalize workspace.section_access to {section_id: [department, ...]}."""
    if not isinstance(raw, dict):
        return {}
    out: dict[str, list[str]] = {}
    for section_id, departments in raw.items():
        sid = str(section_id or "").strip().lower()
        if sid not in MANAGEABLE_SECTION_IDS:
            continue
        if not isinstance(departments, list):
            continue
        cleaned: list[str] = []
        seen: set[str] = set()
        for dept in departments:
            value = str(dept or "").strip()
            if not value:
                continue
            key = value.casefold()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(value)
        if cleaned:
            out[sid] = cleaned
    return out


def normalize_section_grants(raw: Any) -> list[str]:
    """Normalize membership.section_grants to unique manageable section ids."""
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        sid = str(item or "").strip().lower()
        if sid not in MANAGEABLE_SECTION_IDS or sid in seen:
            continue
        seen.add(sid)
        out.append(sid)
    return out


def sections_for_perms(perms: set[str] | frozenset[str] | list[str]) -> list[str]:
    """Map pack permissions to manageable section ids the user already has via pack."""
    perm_set = {str(p or "").strip() for p in (perms or [])}
    out: list[str] = []
    for item in MANAGEABLE_SECTIONS:
        if item["perm"] in perm_set:
            out.append(item["id"])
    return out
