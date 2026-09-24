"""Per-workspace data template for Trenston — Northwind Robotics sample + empty scaffold.

Financials are NOT stored here — they are computed from the `financial_entries`
collection so the finance team can log data straight into Trenston.
"""
import uuid
import secrets
from datetime import datetime, timezone

import integrations_catalog as integ_catalog
import tz_utils
from money_fmt import CURRENCY_SYMBOLS

# New workspaces are Philippines-first; legacy docs without a currency stay usd.
NEW_WORKSPACE_CURRENCY = "php"


def gen_join_code() -> str:
    return secrets.token_urlsafe(9)


def last_n_months(n):
    now = datetime.now(timezone.utc)
    y, m = now.year, now.month
    out = []
    for i in range(n - 1, -1, -1):
        mm, yy = m - i, y
        while mm <= 0:
            mm += 12
            yy -= 1
        out.append(f"{yy:04d}-{mm:02d}")
    return out


def sample_financial_entries(workspace_id):
    """6 months of recurring revenue + categorized expenses (in USD)."""
    REV = [188, 196, 205, 214, 229, 248]
    EXP = [396, 404, 412, 420, 425, 430]
    cats = {"Payroll": 0.62, "Cloud/Infra": 0.14, "Sales & Mktg": 0.12, "G&A": 0.07, "R&D Tools": 0.05}
    now = datetime.now(timezone.utc).isoformat()
    entries = []
    for month, rev, exp in zip(last_n_months(6), REV, EXP):
        entries.append({
            "id": f"fe_{uuid.uuid4().hex[:10]}", "workspace_id": workspace_id, "type": "revenue",
            "category": "Subscriptions", "name": "Subscription MRR", "amount": rev * 1000, "month": month, "recurring": True,
            "note": "Recurring subscription revenue", "source": "manual", "created_by": "seed", "created_at": now,
        })
        names = {
            "Payroll": "Team payroll",
            "Cloud/Infra": "Cloud infrastructure",
            "Sales & Mktg": "Sales and marketing",
            "G&A": "General and administrative",
            "R&D Tools": "Engineering tools",
        }
        for cat, pct in cats.items():
            entries.append({
                "id": f"fe_{uuid.uuid4().hex[:10]}", "workspace_id": workspace_id, "type": "expense",
                "category": cat, "name": names.get(cat, cat), "amount": round(exp * 1000 * pct), "month": month, "recurring": True,
                "note": "", "source": "manual", "created_by": "seed", "created_at": now,
            })
    return entries


def build_workspace(workspace_id, name, owner_user_id, empty=False, currency=None):
    telemetry = {
        "kpis": [
            {"label": "MRR", "value": "$248K", "unit": "", "delta": 8.4, "tone": "positive", "spark": [188, 196, 205, 214, 229, 248]},
            {"label": "Active Customers", "value": "412", "unit": "", "delta": 5.1, "tone": "positive", "spark": [340, 356, 371, 388, 396, 412]},
            {"label": "Net Revenue Retention", "value": "118%", "unit": "", "delta": 2.0, "tone": "positive", "spark": [108, 110, 112, 114, 116, 118]},
            {"label": "CAC Payback", "value": "11.2mo", "unit": "", "delta": -6.0, "tone": "positive", "spark": [14, 13.5, 13, 12.4, 11.8, 11.2]},
            {"label": "Churn (logo)", "value": "2.4%", "unit": "", "delta": 0.6, "tone": "negative", "spark": [1.8, 1.9, 2.0, 2.1, 2.3, 2.4]},
            {"label": "Pipeline", "value": "$1.9M", "unit": "", "delta": 12.0, "tone": "positive", "spark": [1.3, 1.4, 1.5, 1.6, 1.7, 1.9]},
        ],
        "revenue_trend": [], "funnel": [
            {"stage": "Leads", "value": 1240}, {"stage": "Qualified", "value": 486},
            {"stage": "Demo", "value": 214}, {"stage": "Proposal", "value": 96}, {"stage": "Closed Won", "value": 41},
        ],
        "risks": [
            {"id": "r1", "name": "Key AWS cost spike", "likelihood": 3, "impact": 4, "category": "Finance"},
            {"id": "r2", "name": "Lead eng burnout", "likelihood": 4, "impact": 5, "category": "People"},
            {"id": "r3", "name": "Enterprise deal slipping", "likelihood": 3, "impact": 5, "category": "Sales"},
            {"id": "r4", "name": "SOC2 audit delay", "likelihood": 2, "impact": 3, "category": "Compliance"},
            {"id": "r5", "name": "Competitor price cut", "likelihood": 4, "impact": 3, "category": "Market"},
            {"id": "r6", "name": "Supplier lead time", "likelihood": 2, "impact": 2, "category": "Ops"},
        ],
    }

    briefing = {
        "date": "Monday", "greeting": "Good morning",
        "headline": "Revenue is ahead of plan, but capacity risk is rising on engineering.",
        "ai_summary": None, "nrr": {"value": "118%", "delta": 2.0, "tone": "positive"},
        "what_changed": [
            {"title": "Acme Corp enterprise deal moved to Proposal", "detail": "$96K ARR. Champion confirmed budget; legal review next.", "tone": "positive"},
            {"title": "Churn ticked to 2.4%", "detail": "Two SMB logos lost to pricing. Both flagged low usage 30 days prior.", "tone": "negative"},
            {"title": "Cloud spend up 9% WoW", "detail": "New inference cluster left running over weekend.", "tone": "negative"},
            {"title": "NPS rose to 61", "detail": "Q2 survey closed; onboarding revamp is landing.", "tone": "positive"},
        ],
        "what_to_decide": [
            {"id": "d1", "title": "Approve $40K infra reservation", "detail": "Locks 1yr savings plan, cuts cloud 18%.", "urgency": "high"},
            {"id": "d3", "title": "Sign off Acme discount to 12%", "detail": "Closes $96K, sets precedent for enterprise.", "urgency": "high"},
        ],
        "what_to_delegate": [
            {"title": "Draft SMB win-back sequence", "owner": "Maya (Growth)", "detail": "Target the churn cohort within 48h."},
            {"title": "Own SOC2 evidence collection", "owner": "Devin (Eng)", "detail": "Auditor needs artifacts by Friday."},
        ],
    }

    decisions = [
        {"id": "d1", "title": "Approve $40K annual infra reservation", "category": "Finance", "description": "Reserved-capacity plan for the inference cluster.", "recommendation": "Approve: pays back in 4.2 months and cuts cloud spend 18%.", "confidence": 92, "status": "pending", "owner": None, "due": "Today", "impact": "High"},
        {"id": "d2", "title": "Hire second GTM engineer", "category": "People", "description": "Backfill pipeline load; Maya is at 118% utilization.", "recommendation": "Approve conditional: start after Acme closes to protect runway.", "confidence": 74, "status": "pending", "owner": None, "due": "This week", "impact": "Medium"},
        {"id": "d3", "title": "Sign off Acme discount to 12%", "category": "Sales", "description": "Enterprise deal, $96K ARR, 3-yr term requested.", "recommendation": "Approve at 10% with 3-yr lock, which protects ACV and sets a defensible floor.", "confidence": 81, "status": "pending", "owner": None, "due": "Today", "impact": "High"},
        {"id": "d4", "title": "Sunset legacy v1 API", "category": "Product", "description": "18% of infra cost, used by 6 customers.", "recommendation": "Delegate migration plan; deprecate in 90 days with comms.", "confidence": 68, "status": "pending", "owner": None, "due": "Next week", "impact": "Medium"},
        {"id": "d5", "title": "Q3 board deck narrative", "category": "Strategy", "description": "Lead with efficiency or growth?", "recommendation": "Lead with efficient growth: NRR 118% + improving CAC payback is the story.", "confidence": 88, "status": "approved", "owner": "You", "due": "Done", "impact": "High"},
    ]

    tasks = {
        "columns": [
            {"id": "backlog", "name": "To-Do"}, {"id": "in_progress", "name": "In Progress"},
            {"id": "review", "name": "Review"}, {"id": "done", "name": "Done"},
        ],
        "items": [
            {"id": "t1", "title": "Acme security questionnaire", "assignee": "Devin", "priority": "High", "column": "in_progress", "tag": "Sales", "due": "Wed", "progress": 60},
            {"id": "t2", "title": "SMB win-back email sequence", "assignee": "Maya", "priority": "High", "column": "backlog", "tag": "Growth", "due": "Thu", "progress": 0},
            {"id": "t3", "title": "Board deck v1", "assignee": "You", "priority": "High", "column": "in_progress", "tag": "Strategy", "due": "Thu", "progress": 30},
        ],
    }

    reports = [
        {"id": "rep1", "title": "Sales Performance", "type": "Sales", "period": "This week", "summary": "41 closed-won, $96K in late-stage pipeline. Win rate 22%, up 3pts.", "metrics": [{"label": "Closed", "value": "41"}, {"label": "Win rate", "value": "22%"}, {"label": "ACV", "value": "$7.2K"}]},
        {"id": "rep2", "title": "Production / Uptime", "type": "Production", "period": "This week", "summary": "99.98% uptime. One p2 incident (inference latency), resolved in 22m.", "metrics": [{"label": "Uptime", "value": "99.98%"}, {"label": "Incidents", "value": "1"}, {"label": "MTTR", "value": "22m"}]},
        {"id": "rep3", "title": "Procurement", "type": "Procurement", "period": "This month", "summary": "Cloud commit renewal pending. 2 vendor contracts up for review.", "metrics": [{"label": "Open POs", "value": "6"}, {"label": "Spend", "value": "$41K"}, {"label": "Savings", "value": "$7K"}]},
    ]

    team = {
        "members": [],
    }

    calendar = {
        "meetings": [
            {"id": "m1", "title": "Acme final review", "time": "09:30", "duration": 45, "attendees": 4, "type": "Sales", "prep": "Bring 3-yr pricing + security pack. Champion: VP Eng.", "importance": "high"},
            {"id": "m2", "title": "Weekly leadership sync", "time": "11:00", "duration": 30, "attendees": 5, "type": "Internal", "prep": "Decide infra reservation + GTM hire.", "importance": "medium"},
            {"id": "m3", "title": "1:1 with Maya", "time": "14:00", "duration": 30, "attendees": 2, "type": "1:1", "prep": "Address open pipeline load: redistribute or hire.", "importance": "high"},
            {"id": "m4", "title": "Investor update call", "time": "16:00", "duration": 30, "attendees": 3, "type": "Board", "prep": "Lead with NRR 118% and CAC payback trend.", "importance": "medium"},
        ],
        "focus_hours": 3.5, "meeting_hours": 2.25,
    }

    people = {
        "people": [
            {"id": "p1", "name": "Maya Chen", "role": "Head of Growth", "department": "Growth", "tenure": "2.1y"},
            {"id": "p2", "name": "Devin Okoro", "role": "Lead Engineer", "department": "Engineering", "tenure": "3.0y"},
            {"id": "p3", "name": "Priya Nair", "role": "Infra Engineer", "department": "Engineering", "tenure": "1.4y"},
            {"id": "p4", "name": "Leo Martins", "role": "Product Designer", "department": "Product", "tenure": "0.9y"},
            {"id": "p5", "name": "Sara Kim", "role": "Account Executive", "department": "Sales", "tenure": "1.8y"},
            {"id": "p6", "name": "Tom Wells", "role": "Support Lead", "department": "Support", "tenure": "1.2y"},
        ],
    }

    integrations = integ_catalog.INTEGRATION_CATALOG

    if empty:
        telemetry = {"kpis": [], "revenue_trend": [], "funnel": [], "risks": []}
        briefing = {"date": "Today", "greeting": "Good morning", "headline": "Start by logging your financials and adding your team.",
                    "ai_summary": None, "nrr": None, "what_changed": [], "what_to_decide": [], "what_to_delegate": []}
        decisions = []
        tasks = {"columns": [{"id": "backlog", "name": "To-Do"}, {"id": "in_progress", "name": "In Progress"}, {"id": "review", "name": "Review"}, {"id": "done", "name": "Done"}], "items": []}
        reports = []
        team = {"members": []}
        calendar = {"meetings": [], "focus_hours": 0, "meeting_hours": 0}
        people = {"people": []}

    return {
        "workspace_id": workspace_id, "name": name, "owner_user_id": owner_user_id, "plan": "free",
        "stage": "" if empty else "Established, growing",
        "employees": 24 if not empty else 0,
        "founded": "" if empty else "2014",
        "mission": "Autonomous inspection robots for industrial sites." if not empty else "",
        "onboarding_done": not empty, "company_setup_done": not empty,
        "industry": "" if empty else "Industrial Robotics",
        "founder_title": "" if empty else "CEO",
        # Sample template has a team; empty/new leaves has_team unset until CompanySetup.
        "has_team": True if not empty else None,
        "template": "empty" if empty else "sample",
        "timezone": tz_utils.DEFAULT_TZ,
        "join_code": gen_join_code(),
        "financial_settings": {
            "cash": None if empty else 3100000,
            "cash_entered": not empty,
            "gross_margin": None if empty else 74,
            "currency": (
                currency.strip().lower()
                if isinstance(currency, str) and currency.strip().lower() in CURRENCY_SYMBOLS
                else NEW_WORKSPACE_CURRENCY
            ),
        },
        "briefing": briefing, "decisions": decisions, "telemetry": telemetry,
        "tasks": tasks, "reports": [], "manual_reports": ([] if empty else reports), "team": team, "calendar": calendar,
        "people": people, "integrations": integrations,
        "google_tokens": None, "quickbooks_tokens": None, "xero_tokens": None, "hubspot_tokens": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
