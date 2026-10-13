"""Search across a workspace's own records for the Ctrl+K bar.

Plain text matching, no AI. The caller passes in only the records the person is allowed
to see; this module just ranks them, so access rules stay in one place (the endpoint).
"""
from __future__ import annotations

import re
from typing import Any, Iterable

MAX_QUERY = 80
PER_GROUP = 5


def clean_query(q: Any) -> str:
    return re.sub(r"\s+", " ", str(q or "")).strip()[:MAX_QUERY].lower()


def _score(q: str, tokens: list[str], fields: list[str]) -> int:
    """0 = no match. Higher is better: whole phrase at the start of the title wins."""
    title = (fields[0] or "").lower() if fields else ""
    blob = " ".join((f or "").lower() for f in fields)
    if not all(t in blob for t in tokens):
        return 0
    if title.startswith(q):
        return 100
    if q in title:
        return 80
    words = re.split(r"[^a-z0-9]+", title)
    if all(any(w.startswith(t) for w in words) for t in tokens):
        return 60
    if q in blob:
        return 40
    return 20


def _rank(q: str, rows: Iterable[dict], fields_of, shape) -> list[dict]:
    tokens = q.split()
    scored = []
    for i, r in enumerate(rows):
        s = _score(q, tokens, fields_of(r))
        if s:
            scored.append((-s, i, r))
    scored.sort(key=lambda x: (x[0], x[1]))
    return [shape(r) for _, _, r in scored[:PER_GROUP]]


def search_records(q: Any, *, tasks=(), decisions=(), deals=(), members=()) -> dict:
    query = clean_query(q)
    if len(query) < 2:
        return {"query": query, "groups": []}
    groups = []

    t = _rank(
        query, tasks,
        lambda r: [r.get("title"), r.get("assignee"), r.get("tag")],
        lambda r: {
            "id": r.get("id"), "title": r.get("title") or "Untitled task",
            "detail": " · ".join(x for x in [
                "Done" if r.get("column") == "done" else "Open", r.get("assignee"),
                f"due {str(r['due'])[:10]}" if r.get("due") else "",
            ] if x),
            "to": "/app/tasks",
        },
    )
    if t:
        groups.append({"kind": "task", "label": "Tasks", "items": t})

    d = _rank(
        query, decisions,
        lambda r: [r.get("title"), r.get("owner"), r.get("context")],
        lambda r: {
            "id": r.get("id"), "title": r.get("title") or "Untitled decision",
            "detail": " · ".join(x for x in [str(r.get("status") or "").title(), r.get("owner")] if x),
            "to": "/app/decisions",
        },
    )
    if d:
        groups.append({"kind": "decision", "label": "Decisions", "items": d})

    de = _rank(
        query, deals,
        lambda r: [r.get("name"), r.get("company"), r.get("owner_name")],
        lambda r: {
            "id": r.get("id"), "title": r.get("name") or "Untitled deal",
            "detail": " · ".join(x for x in [r.get("company"), str(r.get("stage") or "").title()] if x),
            "to": "/app/sales",
        },
    )
    if de:
        groups.append({"kind": "deal", "label": "Deals", "items": de})

    p = _rank(
        query, [m for m in members if m.get("status") != "invited" or m.get("email")],
        lambda r: [r.get("name") or r.get("email"), r.get("email")],
        lambda r: {
            "id": r.get("user_id") or r.get("membership_id"),
            "title": r.get("name") or r.get("email") or "Teammate",
            "detail": r.get("email") or "",
            "to": "/app/people",
        },
    )
    if p:
        groups.append({"kind": "person", "label": "People", "items": p})

    return {"query": query, "groups": groups}
