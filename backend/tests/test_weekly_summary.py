"""Monday briefing: summary content, money gating, subject line and email HTML."""
from __future__ import annotations

import os
from datetime import date

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_weekly_summary")

import email_compliance as ec  # noqa: E402
import weekly_summary as ws  # noqa: E402

TODAY = date(2026, 10, 19)

WORKSPACE = {
    "decisions": [
        {"id": "d1", "title": "Hire a plant manager", "status": "pending", "due": "Oct 30", "impact": "High"},
        {"id": "d2", "title": "Switch supplier", "status": "pending", "due": "—", "impact": "Medium"},
        {"id": "d3", "title": "Old call", "status": "approved", "due": "—"},
    ],
    "tasks": {"items": [
        {"id": "t1", "title": "Send Q3 report", "assignee": "Sarah", "column": "doing", "due": "2026-10-03"},
        {"id": "t2", "title": "Renew insurance", "assignee": "Ely", "column": "backlog", "due": "2026-10-10"},
        {"id": "t3", "title": "Already done", "assignee": "Ely", "column": "done", "due": "2026-09-01"},
        {"id": "t4", "title": "Next week", "assignee": "Ely", "column": "backlog", "due": "2026-10-22"},
        {"id": "t5", "title": "No date", "assignee": "Ely", "column": "backlog", "due": ""},
    ]},
}

FIN = {
    "cash": "₱500K", "cash_entered": True,
    "burn": "₱120K", "burn_known": True, "burn_value": 120000,
    "runway_months": 4.2, "runway_no_burn": False,
    "runway_basis": "Based on the last 3 full months.",
}


def _build(fin=None, stale=None, workspace=None):
    return ws.build_summary(workspace=workspace or WORKSPACE, fin=fin, stale=stale or [], today=TODAY)


def test_counts_only_pending_decisions_and_open_overdue_tasks():
    s = _build()
    assert s["decision_count"] == 2
    assert [d["title"] for d in s["decisions"]] == ["Hire a plant manager", "Switch supplier"]
    assert s["decisions"][1]["due"] == ""  # the "—" placeholder is not a date
    assert s["overdue_count"] == 2
    assert [t["title"] for t in s["overdue"]] == ["Send Q3 report", "Renew insurance"]  # oldest first
    assert s["due_soon_count"] == 1  # "Next week"; done and undated tasks never count
    assert s["has_content"] is True


def test_money_only_when_figures_were_entered():
    s = _build(fin=FIN)
    labels = dict(s["money"]["rows"])
    assert labels["Cash in the bank"] == "₱500K"
    assert labels["Net monthly burn"] == "₱120K"
    assert labels["Runway"] == "About 4.2 months"
    # No Financials access: nothing about money at all.
    assert _build(fin=None)["money"] is None
    # A founder who never entered cash or burn gets no made-up zeros.
    empty = {"cash_entered": False, "cash": "—", "burn_known": False, "burn": "—", "runway_months": None}
    assert _build(fin=empty)["money"] is None


def test_profit_and_no_burn_are_worded_honestly():
    profit = dict(FIN, burn="-₱30K", burn_value=-30000, runway_months=None, runway_no_burn=True)
    rows = dict(_build(fin=profit)["money"]["rows"])
    assert rows["Monthly surplus"] == "₱30K"
    assert rows["Runway"] == "Cash is not running down"


def test_empty_workspace_has_no_content():
    s = _build(workspace={"decisions": [], "tasks": {"items": []}})
    assert s["has_content"] is False


def test_subject_and_quiet_tolerate_bad_numeric_fields():
    """Malformed runway / days must not crash Monday email assembly."""
    s = _build(fin={**FIN, "runway_months": "n/a"}, stale=[{"name": "Sales", "days_since_update": "x"}])
    assert s["quiet"][0]["days"] == 0
    assert isinstance(ws.subject_for("Acme", s), str)


def test_subject_names_the_company_and_what_needs_attention():
    s = _build(fin=FIN, stale=[{"name": "Sales", "days_since_update": 12, "lead_name": "Ana"}])
    subject = ws.subject_for("Wattwise PH", s)
    assert subject.startswith("Wattwise PH: 2 decisions waiting, 2 tasks overdue")
    assert len(subject) <= ws.SUBJECT_MAX
    quiet = ws.subject_for("Acme", _build(workspace={"decisions": [], "tasks": {"items": []}}, fin=FIN))
    assert "Acme" in quiet


def test_lead_sentence_reads_naturally():
    assert ws.lead_sentence(_build()) == "2 decisions waiting and 2 tasks overdue."
    one = _build(workspace={"decisions": [WORKSPACE["decisions"][0]], "tasks": {"items": []}})
    assert ws.lead_sentence(one) == "1 decision waiting."
    calm = _build(workspace={"decisions": [], "tasks": {"items": []}}, fin=FIN)
    assert ws.lead_sentence(calm).startswith("Nothing is overdue")


def test_email_html_shows_content_escapes_and_has_footer():
    s = _build(fin=FIN, stale=[{"name": "Sales", "days_since_update": 12, "lead_name": "Ana"}])
    s["decisions"][0]["title"] = "Hire <b>now</b>"
    html = ws.email_html(
        workspace_name="Acme & Co", summary=s, app_url="https://www.trenston.com",
        unsubscribe_url="https://www.trenston.com/unsubscribe?token=x", has_pdf=True,
    )
    assert "Acme &amp; Co" in html
    assert "Hire &lt;b&gt;now&lt;/b&gt;" in html and "<b>now</b>" not in html
    assert "₱500K" in html and "About 4.2 months" in html
    assert "Send Q3 report" in html and "Sarah" in html and "was due Oct 3" in html
    assert "No update in 12 days. Ask Ana." in html
    assert "https://www.trenston.com/app/decisions" not in html  # only 2 decisions: no "more" link
    assert "attached as a PDF" in html
    assert "Unsubscribe" in html and ec.COMPANY_POSTAL_ADDRESS in html
    assert "—" not in html  # no em dashes in what a founder reads


def test_email_without_money_has_no_money_block_and_links_to_more():
    many = {"decisions": [{"id": str(i), "title": f"Call {i}", "status": "pending"} for i in range(8)],
            "tasks": {"items": []}}
    s = _build(workspace=many)
    html = ws.email_html(workspace_name="Acme", summary=s, app_url="https://www.trenston.com")
    assert ">Money<" not in html
    assert "See all decisions (3 more)" in html
    assert "https://www.trenston.com/app/decisions" in html
    assert "attached as a PDF" not in html
