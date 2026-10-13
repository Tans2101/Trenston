"""Ctrl+K record search: ranking and grouping, no model."""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_record_search")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import record_search as rs  # noqa: E402

TASKS = [
    {"id": "t1", "title": "Send the supplier invoice", "assignee": "Ann", "column": "backlog", "due": "2026-10-16"},
    {"id": "t2", "title": "Call supplier about delay", "assignee": "Sam", "column": "done"},
    {"id": "t3", "title": "Update roadmap", "assignee": "Ann"},
]
DECISIONS = [{"id": "d1", "title": "Hire a second developer", "status": "pending", "owner": "Tansher"}]
DEALS = [{"id": "x1", "name": "Acme renewal", "company": "Acme Ltd", "stage": "won"}]
MEMBERS = [
    {"user_id": "u1", "name": "Ann Lee", "email": "ann@x.com", "status": "active"},
    {"membership_id": "m2", "email": "pending@x.com", "status": "invited"},
]


def run(q):
    return rs.search_records(q, tasks=TASKS, decisions=DECISIONS, deals=DEALS, members=MEMBERS)


def kinds(r):
    return [g["kind"] for g in r["groups"]]


def test_short_query_returns_nothing():
    assert run("a")["groups"] == []
    assert run("   ")["groups"] == []


def test_title_start_ranks_first():
    r = run("call")
    assert r["groups"][0]["items"][0]["id"] == "t2"


def test_all_words_must_match_in_any_order():
    r = run("invoice supplier")
    ids = [i["id"] for g in r["groups"] for i in g["items"]]
    assert ids == ["t1"]


def test_groups_for_each_record_type():
    assert kinds(run("acme")) == ["deal"]
    assert kinds(run("developer")) == ["decision"]
    assert kinds(run("ann")) == ["task", "person"]


def test_person_and_deal_links():
    assert run("ann")["groups"][-1]["items"][0]["to"] == "/app/people"
    assert run("acme")["groups"][0]["items"][0]["to"] == "/app/sales"


def test_invited_without_name_still_findable_by_email():
    r = run("pending")
    assert r["groups"][0]["items"][0]["title"] == "pending@x.com"


def test_limits_and_case():
    many = [{"id": f"t{i}", "title": f"Supplier {i}"} for i in range(20)]
    r = rs.search_records("SUPPLIER", tasks=many)
    assert len(r["groups"][0]["items"]) == rs.PER_GROUP
    assert r["query"] == "supplier"


def test_empty_and_odd_input():
    assert rs.clean_query(None) == ""
    assert len(rs.clean_query("x" * 500)) == rs.MAX_QUERY
    assert run("zzzz")["groups"] == []
