"""Monday founder summary: the weekly email that tells a CEO what needs them.

Pure functions only (no database), so every figure and sentence is testable.
The caller loads the workspace, the financial snapshot and the quiet-department
list, and this module turns them into a small dict plus an email.

Rules this module keeps:
- Money is shown only when the caller says the reader may see it, and only
  figures the founder really entered. A missing figure is left out, never
  shown as zero.
- Nothing is invented: counts and names come straight from the data.
- An empty week produces no email (has_content is False).
"""
from __future__ import annotations

import html
from datetime import date, datetime, timedelta
from typing import Optional

MAX_DECISIONS = 5
MAX_TASKS = 5
MAX_QUIET = 3
SUBJECT_MAX = 90


def _plural(n: int, one: str, many: Optional[str] = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def _short_date(value: str) -> str:
    """'2026-10-03' -> 'Oct 3'. Unparseable text is returned as given."""
    raw = (value or "").strip()
    try:
        d = datetime.strptime(raw[:10], "%Y-%m-%d")
        return f"{d.strftime('%b')} {d.day}"
    except ValueError:
        return raw


def _decisions(workspace: dict) -> tuple[int, list[dict]]:
    pending = [
        d for d in (workspace.get("decisions") or [])
        if isinstance(d, dict) and d.get("status") == "pending" and (d.get("title") or "").strip()
    ]
    rows = []
    for d in pending[:MAX_DECISIONS]:
        due = (d.get("due") or "").strip()
        rows.append({
            "title": d["title"].strip(),
            "due": "" if due in ("", "—", "-") else due,
            "impact": d.get("impact") or "",
        })
    return len(pending), rows


def _tasks(workspace: dict, today: date) -> dict:
    items = ((workspace.get("tasks") or {}).get("items")) or []
    today_s = today.isoformat()
    soon_s = (today + timedelta(days=7)).isoformat()
    overdue: list[dict] = []
    due_soon = 0
    for t in items:
        if not isinstance(t, dict) or t.get("column") == "done":
            continue
        due = (t.get("due") or "").strip()[:10]
        if not due or len(due) != 10:
            continue
        if due < today_s:
            overdue.append(t)
        elif due <= soon_s:
            due_soon += 1
    overdue.sort(key=lambda t: (t.get("due") or "")[:10])
    rows = []
    for t in overdue[:MAX_TASKS]:
        rows.append({
            "title": (t.get("title") or "Untitled task").strip(),
            "assignee": (t.get("assignee") or "").strip(),
            "due": (t.get("due") or "")[:10],
        })
    return {"overdue_count": len(overdue), "overdue": rows, "due_soon_count": due_soon}


def _runway_text(fin: dict) -> Optional[str]:
    months = fin.get("runway_months")
    if months is not None:
        try:
            m = float(months)
        except (TypeError, ValueError):
            return None
        if m <= 0:
            return "No cash left at the current pace"
        shown = f"{m:.1f}".rstrip("0").rstrip(".") if m < 10 else str(round(m))
        return f"About {shown} {'month' if shown == '1' else 'months'}"
    if fin.get("runway_no_burn"):
        return "Cash is not running down"
    return None


def _money(fin: Optional[dict]) -> Optional[dict]:
    """Only figures the founder entered. None when there is nothing honest to show."""
    if not fin:
        return None
    rows: list[tuple[str, str]] = []
    if fin.get("cash_entered") and fin.get("cash") not in (None, "", "—"):
        rows.append(("Cash in the bank", str(fin["cash"])))
    burn_value = fin.get("burn_value")
    if fin.get("burn_known") and burn_value is not None and fin.get("burn") not in (None, "", "—"):
        if burn_value < 0:
            rows.append(("Monthly surplus", str(fin["burn"]).lstrip("-")))
        else:
            rows.append(("Net monthly burn", str(fin["burn"])))
    runway = _runway_text(fin)
    if runway:
        rows.append(("Runway", runway))
    if not rows:
        return None
    return {
        "rows": rows,
        "runway_months": fin.get("runway_months"),
        "basis": (fin.get("runway_basis") or "").strip() if runway else "",
    }


def _quiet(stale: list[dict]) -> list[dict]:
    out = []
    for a in (stale or [])[:MAX_QUIET]:
        out.append({
            "name": str(a.get("name") or "A department"),
            "days": int(a.get("days_since_update") or 0),
            "lead_name": (a.get("lead_name") or "").strip(),
        })
    return out


def build_summary(
    *,
    workspace: dict,
    fin: Optional[dict],
    stale: Optional[list[dict]],
    today: date,
) -> dict:
    """Everything the email needs. `fin` is None for readers without Financials access."""
    decision_count, decisions = _decisions(workspace)
    tasks = _tasks(workspace, today)
    money = _money(fin)
    quiet = _quiet(stale or [])
    return {
        "decision_count": decision_count,
        "decisions": decisions,
        "overdue_count": tasks["overdue_count"],
        "overdue": tasks["overdue"],
        "due_soon_count": tasks["due_soon_count"],
        "money": money,
        "quiet": quiet,
        "has_content": bool(decision_count or tasks["overdue_count"] or tasks["due_soon_count"] or money or quiet),
    }


def _attention_parts(summary: dict) -> list[str]:
    parts = []
    n = summary.get("decision_count") or 0
    if n:
        parts.append(f"{_plural(n, 'decision')} waiting")
    n = summary.get("overdue_count") or 0
    if n:
        parts.append(f"{_plural(n, 'task')} overdue")
    n = len(summary.get("quiet") or [])
    if n:
        parts.append(f"{_plural(n, 'department')} gone quiet")
    return parts


def subject_for(workspace_name: str, summary: dict) -> str:
    name = (workspace_name or "Your company").strip()
    parts = _attention_parts(summary)
    money = summary.get("money") or {}
    months = money.get("runway_months")
    if months is not None and 0 < float(months) < 12 and len(parts) < 3:
        shown = f"{float(months):.0f}" if float(months) >= 10 else f"{float(months):.1f}".rstrip("0").rstrip(".")
        parts.append(f"about {shown} months of cash")
    subject = f"{name}: " + ", ".join(parts) if parts else f"Your week at {name}"
    return subject if len(subject) <= SUBJECT_MAX else subject[: SUBJECT_MAX - 1].rstrip() + "…"


def lead_sentence(summary: dict) -> str:
    parts = _attention_parts(summary)
    if not parts:
        return "Nothing is overdue and no decisions are waiting. Here is where things stand."
    text = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
    return text[0].upper() + text[1:] + "."


def _row(label: str, value: str) -> str:
    return (
        '<tr><td style="padding:6px 0;color:#a1a1aa;font-size:13px;vertical-align:top;">'
        f"{html.escape(label)}</td>"
        '<td style="padding:6px 0 6px 16px;color:#ffffff;font-size:14px;text-align:right;">'
        f"{html.escape(value)}</td></tr>"
    )


def _block(title: str, inner: str) -> str:
    return (
        '<tr><td style="padding:22px 36px 0 36px;">'
        f'<p style="color:#c9a962;font-size:11px;letter-spacing:2px;text-transform:uppercase;margin:0 0 10px 0;">{html.escape(title)}</p>'
        f"{inner}</td></tr>"
    )


def _item(main: str, sub: str = "") -> str:
    sub_html = (
        f'<br><span style="color:#a1a1aa;font-size:12px;">{html.escape(sub)}</span>' if sub else ""
    )
    return (
        '<p style="color:#ffffff;font-size:14px;line-height:1.5;margin:0 0 10px 0;">'
        f"{html.escape(main)}{sub_html}</p>"
    )


def _more(extra: int, link: str, label: str) -> str:
    if extra <= 0:
        return ""
    return (
        '<p style="margin:0 0 4px 0;font-size:13px;">'
        f'<a href="{html.escape(link, quote=True)}" style="color:#c9a962;text-decoration:underline;">'
        f"{html.escape(label)} ({extra} more)</a></p>"
    )


def email_html(
    *,
    workspace_name: str,
    summary: dict,
    app_url: str,
    unsubscribe_url: str = "",
    has_pdf: bool = False,
) -> str:
    import email_compliance as ec

    base = (app_url or "").rstrip("/")
    name = html.escape(workspace_name or "your company")
    blocks: list[str] = []

    money = summary.get("money")
    if money:
        rows = "".join(_row(label, value) for label, value in money["rows"])
        basis = (
            f'<p style="color:#71717a;font-size:11px;line-height:1.5;margin:6px 0 0 0;">{html.escape(money["basis"])}</p>'
            if money.get("basis") else ""
        )
        blocks.append(_block("Money", f'<table width="100%" cellpadding="0" cellspacing="0">{rows}</table>{basis}'))

    n_dec = summary.get("decision_count") or 0
    if n_dec:
        inner = "".join(
            _item(d["title"], " · ".join(x for x in (f"Due {d['due']}" if d["due"] else "", d["impact"] and f"{d['impact']} impact") if x))
            for d in summary["decisions"]
        ) + _more(n_dec - len(summary["decisions"]), base + "/app/decisions", "See all decisions")
        blocks.append(_block("Waiting on you", inner))

    n_over = summary.get("overdue_count") or 0
    if n_over:
        inner = "".join(
            _item(
                t["title"],
                " · ".join(x for x in (t["assignee"], f"was due {_short_date(t['due'])}") if x),
            )
            for t in summary["overdue"]
        ) + _more(n_over - len(summary["overdue"]), base + "/app/tasks", "See all tasks")
        blocks.append(_block("Overdue", inner))

    soon = summary.get("due_soon_count") or 0
    if soon and not n_over:
        blocks.append(_block("Coming up", _item(f"{_plural(soon, 'task')} due in the next 7 days")))

    quiet = summary.get("quiet") or []
    if quiet:
        inner = "".join(
            _item(
                q["name"],
                f"No update in {q['days']} days" + (f". Ask {q['lead_name']}." if q["lead_name"] else "."),
            )
            for q in quiet
        )
        blocks.append(_block("Gone quiet", inner))

    pdf_line = (
        '<tr><td style="padding:18px 36px 0 36px;">'
        '<p style="color:#a1a1aa;font-size:13px;line-height:1.6;margin:0;">'
        "Your full CEO pack is attached as a PDF.</p></td></tr>"
        if has_pdf else ""
    )
    footer = (
        ec.marketing_footer_html(unsubscribe_url=unsubscribe_url)
        if unsubscribe_url
        else ""
    )
    return f"""\
<!DOCTYPE html><html><body style="margin:0;padding:0;background:#09090b;font-family:Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#09090b;padding:32px 12px;">
<tr><td align="center">
<table width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;background:#121214;border:1px solid rgba(255,255,255,0.08);border-radius:14px;overflow:hidden;">
<tr><td style="padding:32px 36px 4px 36px;">
<p style="color:#c9a962;font-size:11px;letter-spacing:2px;text-transform:uppercase;margin:0;">Monday briefing</p>
<h1 style="color:#ffffff;font-size:22px;font-weight:400;margin:10px 0 0 0;line-height:1.3;">Your week at<br><span style="color:#c9a962;">{name}</span></h1>
<p style="color:#ffffff;font-size:15px;line-height:1.6;margin:14px 0 0 0;">{html.escape(lead_sentence(summary))}</p>
</td></tr>
{''.join(blocks)}
<tr><td style="padding:28px 36px 8px 36px;">
<table cellpadding="0" cellspacing="0"><tr>
<td style="background:#c9a962;border-radius:8px;">
<a href="{html.escape(base + '/app', quote=True)}" style="display:inline-block;padding:12px 26px;color:#09090b;font-size:14px;font-weight:600;text-decoration:none;">Open your Briefing &rarr;</a>
</td></tr></table>
</td></tr>
{pdf_line}
{footer}
</table>
</td></tr></table></body></html>"""
