"""Custom dashboards: a service sold on top of Trenston for larger companies.

A client company contacts Trenston (public inquiry form), the work is scoped by
hand, and the Trenston operator turns on a custom dashboard for that company's
workspace. The client keeps all of normal Trenston and gets one extra section
built from a widget config. People reach it by signing in with an approved
email address (each approved email is invited into the workspace).

This module is pure logic: the widget catalog, config validation, inquiry
validation and the operator email. server.py owns the routes and data access.
"""
from __future__ import annotations

import html
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

TIERS = ("configured", "tailored", "bespoke")
TIER_LABELS = {
    "configured": "Configured (about 70% standard)",
    "tailored": "Tailored (about 60% standard)",
    "bespoke": "Bespoke (about 50% standard)",
}

BUDGET_RANGES = (
    "under_2k",
    "2k_5k",
    "5k_10k",
    "10k_plus",
    "not_sure",
)
BUDGET_LABELS = {
    "under_2k": "Under $2,000",
    "2k_5k": "$2,000 to $5,000",
    "5k_10k": "$5,000 to $10,000",
    "10k_plus": "$10,000+",
    "not_sure": "Not sure yet",
}
COMPANY_SIZES = ("1_10", "11_50", "51_200", "201_1000", "1000_plus")
COMPANY_SIZE_LABELS = {
    "1_10": "1 to 10 people",
    "11_50": "11 to 50 people",
    "51_200": "51 to 200 people",
    "201_1000": "201 to 1,000 people",
    "1000_plus": "1,000+ people",
}
INQUIRY_STATUSES = ("new", "contacted", "scoping", "won", "lost")

FINANCIAL_METRICS = ("mrr", "arr", "burn", "cash", "runway_months", "gross_margin")
FINANCIAL_METRIC_LABELS = {
    "mrr": "Monthly revenue",
    "arr": "Annual run rate",
    "burn": "Monthly burn",
    "cash": "Cash",
    "runway_months": "Runway",
    "gross_margin": "Gross margin",
}
TONES = ("neutral", "positive", "negative", "warning")

# type -> whether it reads money figures (needs Financials access to show data)
WIDGET_TYPES: dict[str, dict[str, Any]] = {
    "financial_kpi": {"label": "Financial figure", "financial": True},
    "revenue_expenses_chart": {"label": "Revenue vs expenses chart", "financial": True},
    "tasks_summary": {"label": "Tasks: open and overdue", "financial": False},
    "decisions_open": {"label": "Open decisions", "financial": False},
    "briefing_headline": {"label": "Briefing headline", "financial": False},
    "manual_kpi": {"label": "Figure you enter", "financial": False},
    "manual_table": {"label": "Table you enter", "financial": False},
    "note": {"label": "Text note", "financial": False},
    "custom": {"label": "Bespoke component (built in code)", "financial": False},
}

# What a client reads when the operator leaves a widget title blank.
DEFAULT_TITLES = {
    "revenue_expenses_chart": "Revenue and expenses",
    "tasks_summary": "Tasks",
    "decisions_open": "Open decisions",
    "briefing_headline": "Today",
    "manual_kpi": "Figure",
    "manual_table": "Table",
    "note": "Note",
    "custom": "Custom view",
}

MAX_WIDGETS = 40
MAX_APPROVED_EMAILS = 200
MAX_TABLE_COLUMNS = 8
MAX_TABLE_ROWS = 50
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_COMPONENT_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class ConfigError(ValueError):
    """Raised with a message safe to show to the operator."""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_email(raw: Any) -> str:
    return str(raw or "").strip().lower()


def is_valid_email(raw: Any) -> bool:
    email = normalize_email(raw)
    return bool(email) and len(email) <= 254 and bool(_EMAIL_RE.match(email))


def _text(raw: Any, limit: int, *, field: str, required: bool = False) -> str:
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(raw or "")).strip()
    if required and not value:
        raise ConfigError(f"{field} is required")
    if len(value) > limit:
        raise ConfigError(f"{field} must be {limit} characters or fewer")
    return value


def _choice(raw: Any, options: tuple, default: Optional[str], *, field: str) -> Optional[str]:
    value = str(raw or "").strip().lower()
    if not value:
        return default
    if value not in options:
        raise ConfigError(f"{field} must be one of: {', '.join(options)}")
    return value


# ----------------------------------------------------------------- inquiries

def validate_inquiry(raw: Any) -> dict:
    """Clean a public inquiry. Raises ConfigError with a visitor-safe message."""
    if not isinstance(raw, dict):
        raise ConfigError("Send the form as JSON")
    email = normalize_email(raw.get("email"))
    if not is_valid_email(email):
        raise ConfigError("Enter a valid work email")
    return {
        "name": _text(raw.get("name"), 120, field="Your name", required=True),
        "email": email,
        "company": _text(raw.get("company"), 160, field="Company", required=True),
        "role": _text(raw.get("role"), 120, field="Role"),
        "company_size": _choice(raw.get("company_size"), COMPANY_SIZES, None, field="Company size"),
        "tools": _text(raw.get("tools"), 1000, field="Tools you use"),
        "needs": _text(raw.get("needs"), 4000, field="What you want to see", required=True),
        "budget_range": _choice(raw.get("budget_range"), BUDGET_RANGES, "not_sure", field="Budget"),
    }


def is_spam_honeypot(raw: Any) -> bool:
    """The form has a hidden 'website' field people never fill in."""
    return isinstance(raw, dict) and bool(str(raw.get("website") or "").strip())


def inquiry_doc(clean: dict, *, ip: str = "") -> dict:
    # The IP is only used for rate limiting and is deliberately not stored.
    return {
        "inquiry_id": f"inq_{uuid.uuid4().hex[:12]}",
        **clean,
        "status": "new",
        "notes": "",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }


def inquiry_email_html(doc: dict) -> str:
    rows = [
        ("Name", doc.get("name")),
        ("Email", doc.get("email")),
        ("Company", doc.get("company")),
        ("Role", doc.get("role")),
        ("Company size", COMPANY_SIZE_LABELS.get(doc.get("company_size") or "", "")),
        ("Budget", BUDGET_LABELS.get(doc.get("budget_range") or "", "")),
        ("Tools they use", doc.get("tools")),
        ("What they want", doc.get("needs")),
    ]
    body = "".join(
        f'<tr><td style="padding:6px 12px 6px 0;color:#71717a;vertical-align:top;white-space:nowrap">{html.escape(k)}</td>'
        f'<td style="padding:6px 0;color:#0a0a0a;white-space:pre-wrap">{html.escape(str(v or "-"))}</td></tr>'
        for k, v in rows
    )
    return (
        '<div style="font-family:Arial,sans-serif;font-size:14px;line-height:1.5">'
        "<h2 style=\"margin:0 0 12px\">New custom dashboard inquiry</h2>"
        f'<table style="border-collapse:collapse">{body}</table>'
        '<p style="color:#71717a;font-size:12px;margin-top:16px">Reply to this email to reach them. '
        "Manage inquiries in Trenston under Custom clients.</p></div>"
    )


# ----------------------------------------------------------------- widgets

def _clean_params(wtype: str, raw: Any) -> dict:
    p = raw if isinstance(raw, dict) else {}
    if wtype == "financial_kpi":
        metric = _choice(p.get("metric"), FINANCIAL_METRICS, None, field="Financial figure")
        if not metric:
            raise ConfigError("Pick which financial figure to show")
        return {"metric": metric}
    if wtype == "revenue_expenses_chart":
        months = p.get("months", 6)
        try:
            months = int(months)
        except (TypeError, ValueError):
            raise ConfigError("Months must be a number")
        return {"months": max(3, min(24, months))}
    if wtype in ("tasks_summary", "decisions_open"):
        limit = p.get("limit", 5)
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            raise ConfigError("Rows must be a number")
        return {"limit": max(0, min(20, limit))}
    if wtype == "briefing_headline":
        return {}
    if wtype == "manual_kpi":
        return {
            "value": _text(p.get("value"), 40, field="Value", required=True),
            "target": _text(p.get("target"), 40, field="Target"),
            "caption": _text(p.get("caption"), 200, field="Caption"),
            "tone": _choice(p.get("tone"), TONES, "neutral", field="Tone"),
        }
    if wtype == "manual_table":
        cols_raw = p.get("columns") or []
        rows_raw = p.get("rows") or []
        if not isinstance(cols_raw, list) or not isinstance(rows_raw, list):
            raise ConfigError("Table columns and rows must be lists")
        if not cols_raw or len(cols_raw) > MAX_TABLE_COLUMNS:
            raise ConfigError(f"A table needs 1 to {MAX_TABLE_COLUMNS} columns")
        if len(rows_raw) > MAX_TABLE_ROWS:
            raise ConfigError(f"A table can have at most {MAX_TABLE_ROWS} rows")
        columns = [_text(c, 60, field="Column name", required=True) for c in cols_raw]
        rows = []
        for r in rows_raw:
            if not isinstance(r, list):
                raise ConfigError("Each table row must be a list of cells")
            cells = [_text(c, 200, field="Cell") for c in r[: len(columns)]]
            cells += [""] * (len(columns) - len(cells))
            rows.append(cells)
        return {"columns": columns, "rows": rows}
    if wtype == "note":
        return {"body": _text(p.get("body"), 4000, field="Note", required=True)}
    if wtype == "custom":
        component = str(p.get("component") or "").strip().lower()
        if not _COMPONENT_RE.match(component):
            raise ConfigError("Bespoke component id must be lowercase letters, numbers, - or _")
        props = p.get("props") or {}
        if not isinstance(props, dict):
            raise ConfigError("Bespoke component props must be an object")
        if len(str(props)) > 8000:
            raise ConfigError("Bespoke component props are too large")
        return {"component": component, "props": props}
    raise ConfigError("Unknown widget type")


def clean_widget(raw: Any) -> dict:
    if not isinstance(raw, dict):
        raise ConfigError("Each widget must be an object")
    wtype = str(raw.get("type") or "").strip()
    if wtype not in WIDGET_TYPES:
        raise ConfigError(f"Unknown widget type: {wtype or '(blank)'}")
    width = raw.get("width", 1)
    try:
        width = int(width)
    except (TypeError, ValueError):
        width = 1
    wid = str(raw.get("id") or "").strip()
    if not re.match(r"^[A-Za-z0-9_-]{1,40}$", wid):
        wid = f"w_{uuid.uuid4().hex[:8]}"
    default_title = DEFAULT_TITLES.get(wtype, WIDGET_TYPES[wtype]["label"])
    if wtype == "financial_kpi":
        metric = (raw.get("params") or {}).get("metric") if isinstance(raw.get("params"), dict) else None
        default_title = FINANCIAL_METRIC_LABELS.get(str(metric or ""), default_title)
    return {
        "id": wid,
        "type": wtype,
        "title": _text(raw.get("title"), 120, field="Widget title") or default_title,
        "width": max(1, min(3, width)),
        "params": _clean_params(wtype, raw.get("params")),
    }


def clean_widgets(raw: Any) -> list[dict]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ConfigError("Widgets must be a list")
    if len(raw) > MAX_WIDGETS:
        raise ConfigError(f"A dashboard can have at most {MAX_WIDGETS} widgets")
    out, seen = [], set()
    for item in raw:
        w = clean_widget(item)
        while w["id"] in seen:
            w["id"] = f"w_{uuid.uuid4().hex[:8]}"
        seen.add(w["id"])
        out.append(w)
    return out


def default_config(*, title: str, tier: str = "configured", approved_emails: Optional[list] = None) -> dict:
    """A useful starting layout made only of standard widgets."""
    return {
        "enabled": True,
        "title": title[:120] or "Custom dashboard",
        "subtitle": "",
        "tier": tier if tier in TIERS else "configured",
        "restrict_to_approved": False,
        "approved_emails": sorted({normalize_email(e) for e in (approved_emails or []) if is_valid_email(e)}),
        "widgets": clean_widgets([
            {"id": "headline", "type": "briefing_headline", "width": 3},
            {"id": "cash", "type": "financial_kpi", "params": {"metric": "cash"}},
            {"id": "burn", "type": "financial_kpi", "params": {"metric": "burn"}},
            {"id": "runway", "type": "financial_kpi", "params": {"metric": "runway_months"}},
            {"id": "rev_exp", "type": "revenue_expenses_chart", "width": 2, "params": {"months": 6}},
            {"id": "tasks", "type": "tasks_summary", "params": {"limit": 5}},
            {"id": "decisions", "type": "decisions_open", "width": 3, "params": {"limit": 5}},
        ]),
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }


def clean_config_update(raw: Any, current: dict) -> dict:
    """Merge an operator edit into the stored config. Approved emails are managed separately."""
    if not isinstance(raw, dict):
        raise ConfigError("Send the dashboard config as an object")
    out = dict(current or {})
    if "title" in raw:
        out["title"] = _text(raw.get("title"), 120, field="Dashboard title", required=True)
    if "subtitle" in raw:
        out["subtitle"] = _text(raw.get("subtitle"), 240, field="Subtitle")
    if "tier" in raw:
        out["tier"] = _choice(raw.get("tier"), TIERS, "configured", field="Tier")
    if "enabled" in raw:
        out["enabled"] = bool(raw.get("enabled"))
    if "restrict_to_approved" in raw:
        out["restrict_to_approved"] = bool(raw.get("restrict_to_approved"))
    if "widgets" in raw:
        out["widgets"] = clean_widgets(raw.get("widgets"))
    out["updated_at"] = now_iso()
    return out


def can_view(config: Optional[dict], principal: dict) -> bool:
    """Who may open the custom section of a workspace they already belong to."""
    if not config or not config.get("enabled"):
        return False
    if principal.get("pack") == "owner" or principal.get("role") == "owner":
        return True
    if not config.get("restrict_to_approved"):
        return True
    approved = {normalize_email(e) for e in config.get("approved_emails") or []}
    return normalize_email(principal.get("email")) in approved


def needs_financials(widgets: list[dict]) -> bool:
    return any(WIDGET_TYPES.get(w.get("type"), {}).get("financial") for w in widgets or [])


def resolve_widget(widget: dict, sources: dict) -> dict:
    """Attach data to one widget. `sources` holds what server.py already loaded.

    Keys in sources: financials (public_api.financials shape or None),
    financials_access (bool), tasks (list), decisions (list), briefing (dict),
    and errors (set of source names that failed to load).
    """
    w = dict(widget)
    wtype = w.get("type")
    params = w.get("params") or {}
    errors = sources.get("errors") or set()
    if WIDGET_TYPES.get(wtype, {}).get("financial"):
        if not sources.get("financials_access"):
            w["data"] = {"state": "restricted"}
            return w
        if "financials" in errors or not sources.get("financials"):
            w["data"] = {"state": "error"}
            return w
        fin = sources["financials"]
        if wtype == "financial_kpi":
            metric = params.get("metric")
            if metric == "runway_months":
                state = fin.get("runway_state") or "not_entered"
                months = fin.get("runway_months")
                w["data"] = {
                    "state": state,
                    "display": (f"{months} months" if isinstance(months, (int, float)) else months)
                    if state != "not_entered" else None,
                }
            elif metric == "gross_margin":
                gm = fin.get("gross_margin")
                w["data"] = {"state": "ok" if gm else "not_entered", "display": gm}
            else:
                fig = fin.get(metric) or {}
                w["data"] = {"state": fig.get("state") or "not_entered", "display": fig.get("display")}
            w["data"]["currency"] = fin.get("currency")
            return w
        months = (fin.get("monthly") or [])[-int(params.get("months") or 6):]
        w["data"] = {"state": "ok" if months else "not_entered", "months": months, "currency": fin.get("currency")}
        return w
    if wtype == "tasks_summary":
        if "tasks" in errors:
            w["data"] = {"state": "error"}
            return w
        open_tasks = [t for t in sources.get("tasks") or [] if not t.get("done")]
        overdue = [t for t in open_tasks if t.get("overdue")]
        ordered = overdue + [t for t in open_tasks if not t.get("overdue")]
        w["data"] = {
            "state": "ok",
            "open": len(open_tasks),
            "overdue": len(overdue),
            "items": [
                {k: t.get(k) for k in ("title", "assignee", "due", "overdue", "status")}
                for t in ordered[: int(params.get("limit") or 0)]
            ],
        }
        return w
    if wtype == "decisions_open":
        if "decisions" in errors:
            w["data"] = {"state": "error"}
            return w
        open_items = [
            d for d in sources.get("decisions") or []
            # Decisions resolve as approved or rejected (server._DECISION_TERMINAL).
            if str(d.get("status") or "pending").lower() not in ("approved", "rejected")
        ]
        w["data"] = {
            "state": "ok",
            "open": len(open_items),
            "items": [
                {k: d.get(k) for k in ("title", "category", "due", "owner", "status")}
                for d in open_items[: int(params.get("limit") or 0)]
            ],
        }
        return w
    if wtype == "briefing_headline":
        if "briefing" in errors:
            w["data"] = {"state": "error"}
            return w
        b = sources.get("briefing") or {}
        w["data"] = {"state": "ok", "headline": b.get("headline"), "summary": b.get("summary"), "date": b.get("date")}
        return w
    # manual_kpi, manual_table, note, custom: everything lives in params.
    w["data"] = {"state": "ok"}
    return w


def preview_sources() -> dict:
    """Placeholder data for the operator's preview. Never reads a client's records."""
    return {
        "financials_access": True,
        "financials": {
            "currency": "USD",
            "mrr": {"display": "$48,200", "state": "entered"},
            "arr": {"display": "$578,400", "state": "entered"},
            "burn": {"display": "$31,500", "state": "entered"},
            "cash": {"display": "$412,000", "state": "entered"},
            "runway_months": 13.1,
            "runway_state": "entered",
            "gross_margin": "64%",
            "monthly": [
                {"month": m, "revenue": r, "expenses": e}
                for m, r, e in (
                    ("2026-05", 39000, 33000), ("2026-06", 41000, 32500), ("2026-07", 42500, 34000),
                    ("2026-08", 44800, 31800), ("2026-09", 46100, 32900), ("2026-10", 48200, 31500),
                )
            ],
        },
        "tasks": [
            {"title": "Sample: close September books", "assignee": "Finance lead", "due": "2026-10-20", "overdue": True, "done": False, "status": "In progress"},
            {"title": "Sample: renew supplier contract", "assignee": "Operations", "due": "2026-10-28", "overdue": False, "done": False, "status": "To do"},
        ],
        "decisions": [
            {"title": "Sample: approve second production shift", "category": "Operations", "due": "2026-10-25", "owner": "CEO", "status": "open"},
        ],
        "briefing": {"headline": "Sample headline: revenue up 5% this month, two tasks overdue.", "summary": None, "date": None},
        "errors": set(),
    }


def public_config(config: dict) -> dict:
    """What a client member receives (no approved-email list)."""
    return {
        "enabled": bool(config.get("enabled")),
        "title": config.get("title") or "Custom dashboard",
        "subtitle": config.get("subtitle") or "",
        "updated_at": config.get("updated_at"),
    }


def catalog() -> dict:
    return {
        "widget_types": [{"type": k, **v} for k, v in WIDGET_TYPES.items()],
        "financial_metrics": [{"id": k, "label": FINANCIAL_METRIC_LABELS[k]} for k in FINANCIAL_METRICS],
        "tones": list(TONES),
        "tiers": [{"id": t, "label": TIER_LABELS[t]} for t in TIERS],
        "inquiry_statuses": list(INQUIRY_STATUSES),
        "budget_labels": BUDGET_LABELS,
        "company_size_labels": COMPANY_SIZE_LABELS,
    }
