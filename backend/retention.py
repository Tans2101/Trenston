"""Daily retention emails: trial-ending reminder and inactivity nudge.

Invoked by POST /api/internal/run-retention-checks (Render cron), not an in-process scheduler.
"""
from __future__ import annotations

import html
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from plan_usage import parse_dt
from decision_engine import is_financial_signal, is_task_overdue

logger = logging.getLogger("helm.retention")

TRIAL_REMINDER_WINDOW = timedelta(days=2, hours=12)
INACTIVITY_DAYS = 5
MAX_WORKSPACES_PER_RUN = 400
MAX_BULLETS = 6


def trial_end_from_paddle_payload(data: dict | None) -> Optional[str]:
    """Paddle Billing: next_billed_at (trial conversion) or current period end."""
    data = data or {}
    period = data.get("current_billing_period") or {}
    raw = data.get("next_billed_at") or period.get("ends_at")
    if not raw:
        return None
    parsed = parse_dt(raw)
    return parsed.isoformat() if parsed else str(raw)


def effective_trial_end(ws: dict | None, trial_days: int) -> Optional[datetime]:
    ws = ws or {}
    end = parse_dt(ws.get("trial_ends_at"))
    if end:
        return end
    start = parse_dt(ws.get("subscription_started_at")) or parse_dt(ws.get("billing_period_start"))
    if start and trial_days > 0:
        return start + timedelta(days=trial_days)
    return None


def last_activity_at(ws: dict | None) -> Optional[datetime]:
    ws = ws or {}
    return parse_dt(ws.get("last_active_at")) or parse_dt(ws.get("created_at"))


def trial_reminder_due(ws: dict | None, *, now: datetime, trial_days: int) -> bool:
    ws = ws or {}
    status = (ws.get("subscription_status") or ws.get("billing_status") or "").lower()
    if status != "trialing":
        return False
    if ws.get("trial_reminder_sent") is True:
        return False
    end = effective_trial_end(ws, trial_days)
    if not end:
        return False
    remaining = end - now
    return timedelta(0) < remaining <= TRIAL_REMINDER_WINDOW


def inactivity_nudge_due(ws: dict | None, *, now: datetime) -> bool:
    ws = ws or {}
    # Founders who finished CompanySetup but bounced at the template screen
    # still have onboarding_done=False — they are exactly who a win-back
    # nudge is for. Only skip when neither setup flag is set.
    if ws.get("onboarding_done") is False and not ws.get("company_setup_done"):
        return False
    last = last_activity_at(ws)
    if not last:
        return False
    if now - last < timedelta(days=INACTIVITY_DAYS):
        return False
    nudged = parse_dt(ws.get("inactivity_nudge_sent_at"))
    if nudged and nudged >= last:
        return False
    return True


def days_inactive(ws: dict | None, *, now: datetime) -> int:
    last = last_activity_at(ws)
    if not last:
        return 0
    return max(INACTIVITY_DAYS, int((now - last).total_seconds() // 86400))


def collect_change_bullets(
    ws: dict | None,
    *,
    deals: list | None = None,
    activities: list | None = None,
    now: datetime | None = None,
) -> list[str]:
    """Concrete, workspace-specific lines — empty list means skip the email."""
    ws = ws or {}
    now = now or datetime.now(timezone.utc)
    bullets: list[str] = []

    pending = [
        d for d in (ws.get("decisions") or [])
        if d.get("status") == "pending" and (d.get("title") or "").strip()
        and not is_financial_signal(d)
    ]
    for d in pending[:3]:
        bullets.append(f"Open decision: {d['title'].strip()}")

    tasks = ((ws.get("tasks") or {}).get("items") or [])
    overdue = [t for t in tasks if is_task_overdue(t, now.date()) and (t.get("title") or "").strip()]
    for t in overdue[:3]:
        bullets.append(f"Overdue task: {t['title'].strip()}")

    for deal in (deals or [])[:3]:
        name = (deal.get("name") or deal.get("company") or "").strip()
        if not name:
            continue
        stage = (deal.get("stage") or "").strip()
        line = f"Pipeline: {name}"
        if stage:
            line += f" ({stage})"
        bullets.append(line)

    for s in (ws.get("decision_suggestions") or []):
        if s.get("status") != "suggested":
            continue
        # Recipients may lack Financials access; keep cash/burn/revenue alerts out.
        if is_financial_signal(s):
            continue
        sev = (s.get("severity") or (s.get("signal") or {}).get("severity") or "").lower()
        title = (s.get("title") or (s.get("signal") or {}).get("summary") or "").strip()
        if sev == "high" and title:
            bullets.append(f"Trenston signal: {title}")
        if len(bullets) >= MAX_BULLETS:
            break

    if len(bullets) < 2:
        for a in (activities or []):
            summary = (a.get("summary") or "").strip()
            if summary:
                bullets.append(summary)
            if len(bullets) >= MAX_BULLETS:
                break

    # De-dupe while preserving order
    seen = set()
    out = []
    for b in bullets:
        if b in seen:
            continue
        seen.add(b)
        out.append(b)
        if len(out) >= MAX_BULLETS:
            break
    return out


def _esc(s: Any) -> str:
    return html.escape(str(s or ""), quote=True)


def _email_shell(
    *,
    kicker: str,
    heading: str,
    intro: str,
    bullets: list[str],
    cta_url: str,
    cta_label: str,
    unsubscribe_url: str = "",
) -> str:
    import email_compliance as ec

    items = "".join(
        f"<li style='margin:0 0 8px 0;color:#e4e4e7;'>{_esc(b)}</li>" for b in bullets
    )
    footer = ""
    if unsubscribe_url:
        footer = ec.marketing_footer_html(unsubscribe_url=unsubscribe_url)
    return f"""\
<!DOCTYPE html><html><body style="margin:0;padding:0;background:#09090b;font-family:'Helvetica Neue',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#09090b;padding:40px 0;">
<tr><td align="center">
<table width="520" cellpadding="0" cellspacing="0" style="background:#121214;border:1px solid rgba(255,255,255,0.08);border-radius:14px;overflow:hidden;">
<tr><td style="padding:32px 36px 28px 36px;">
<p style="color:#c9a962;font-size:11px;letter-spacing:2px;text-transform:uppercase;margin:0;">{_esc(kicker)}</p>
<h1 style="color:#ffffff;font-size:22px;font-weight:400;margin:10px 0 0 0;line-height:1.3;">{_esc(heading)}</h1>
<p style="color:#a1a1aa;font-size:15px;line-height:1.6;margin:16px 0 0 0;">{intro}</p>
<ul style="margin:18px 0 0 0;padding-left:18px;">{items}</ul>
<table cellpadding="0" cellspacing="0" style="margin:28px 0 8px 0;"><tr>
<td style="background:#c9a962;border-radius:8px;">
<a href="{_esc(cta_url)}" style="display:inline-block;padding:12px 26px;color:#09090b;font-size:14px;font-weight:600;text-decoration:none;">{_esc(cta_label)}</a>
</td></tr></table>
</td></tr>
{footer}
</table>
</td></tr></table></body></html>"""


def trial_email_html(
    *,
    workspace_name: str,
    bullets: list[str],
    briefing_url: str,
    unsubscribe_url: str = "",
) -> str:
    name = workspace_name or "your company"
    intro = (
        f"Your Trenston trial for <b style='color:#ffffff;'>{_esc(name)}</b> ends in 2 days. "
        "If you stay on the plan, the card on file will be charged when the trial converts. "
        "Here's what you'd be keeping:"
    )
    return _email_shell(
        kicker="Trial ending",
        heading="Your Trenston trial ends in 2 days",
        intro=intro,
        bullets=bullets,
        cta_url=briefing_url,
        cta_label="Open your briefing →",
        unsubscribe_url=unsubscribe_url,
    )


def inactivity_email_html(
    *,
    workspace_name: str,
    days: int,
    bullets: list[str],
    briefing_url: str,
    unsubscribe_url: str = "",
) -> str:
    name = workspace_name or "your company"
    intro = (
        f"Your last briefing for <b style='color:#ffffff;'>{_esc(name)}</b> was {days} days ago. "
        "Here's what changed while you were away:"
    )
    return _email_shell(
        kicker="Catch up",
        heading=f"Your last briefing was {days} days ago. Here's what's changed since",
        intro=intro,
        bullets=bullets,
        cta_url=briefing_url,
        cta_label="Open your briefing →",
        unsubscribe_url=unsubscribe_url,
    )


def briefing_url(app_base_url: str) -> str:
    return f"{(app_base_url or '').rstrip('/')}/app"


async def _load_since_docs(db, workspace_id: str, since_iso: str) -> tuple[list, list]:
    deals = await db.deals.find(
        {
            "workspace_id": workspace_id,
            "$or": [
                {"updated_at": {"$gte": since_iso}},
                {"created_at": {"$gte": since_iso}},
            ],
        },
        {"_id": 0, "name": 1, "company": 1, "stage": 1, "value": 1},
    ).sort("updated_at", -1).to_list(8)
    acts = await db.activities.find(
        {"workspace_id": workspace_id, "created_at": {"$gte": since_iso}},
        {"_id": 0, "summary": 1, "created_at": 1},
    ).sort("created_at", -1).to_list(8)
    return deals, acts


async def run_retention_checks(
    db,
    *,
    now: datetime | None = None,
    trial_days: int = 7,
    app_base_url: str = "",
    send_email,
    recipient_emails,
    signing_secret: str = "",
    api_base_url: str = "",
) -> dict:
    """Scan workspaces and send at most one trial reminder / one inactivity nudge per window.

    Commercial emails: skip suppressed addresses, attach CAN-SPAM footer + List-Unsubscribe.
    """
    import email_compliance as ec

    now = now or datetime.now(timezone.utc)
    link = briefing_url(app_base_url)
    secret = (signing_secret or "").strip()
    api_base = (api_base_url or app_base_url or "").rstrip("/")
    stats = {
        "trial_sent": 0,
        "trial_skipped": 0,
        "inactivity_sent": 0,
        "inactivity_skipped": 0,
        "suppressed_skipped": 0,
    }

    trialing = await db.workspaces.find(
        {"$or": [
            {"subscription_status": "trialing"},
            {"billing_status": "trialing"},
        ]},
        {"_id": 0},
    ).to_list(MAX_WORKSPACES_PER_RUN)

    cutoff = (now - timedelta(days=INACTIVITY_DAYS)).isoformat()
    inactive = await db.workspaces.find(
        {"$or": [
            {"last_active_at": {"$lte": cutoff}},
            {"last_active_at": {"$exists": False}, "created_at": {"$lte": cutoff}},
        ]},
        {"_id": 0},
    ).to_list(MAX_WORKSPACES_PER_RUN)

    seen_ids: set[str] = set()
    candidates: list[dict] = []
    for ws in list(trialing) + list(inactive):
        wid = ws.get("workspace_id")
        if not wid or wid in seen_ids:
            continue
        seen_ids.add(wid)
        candidates.append(ws)

    for ws in candidates:
        wid = ws["workspace_id"]
        last = last_activity_at(ws) or now - timedelta(days=INACTIVITY_DAYS)
        since_iso = last.isoformat()
        try:
            deals, acts = await _load_since_docs(db, wid, since_iso)
            bullets = collect_change_bullets(ws, deals=deals, activities=acts, now=now)
            emails = await recipient_emails(wid)
            name = ws.get("name") or "your company"

            if trial_reminder_due(ws, now=now, trial_days=trial_days):
                if not bullets or not emails:
                    stats["trial_skipped"] += 1
                else:
                    sendable = await ec.filter_unsuppressed(db, emails) if secret else list(emails)
                    if not sendable:
                        stats["suppressed_skipped"] += 1
                        stats["trial_skipped"] += 1
                    else:
                        any_sent = False
                        for addr in sendable:
                            unsub = (
                                ec.unsubscribe_url(app_base_url, addr, secret=secret)
                                if secret else ""
                            )
                            headers = {}
                            if secret and api_base:
                                one_click = ec.api_unsubscribe_url(api_base, addr, secret=secret)
                                headers = ec.list_unsubscribe_headers(one_click)
                            result = await send_email(
                                addr,
                                "Your Trenston trial ends in 2 days",
                                trial_email_html(
                                    workspace_name=name,
                                    bullets=bullets,
                                    briefing_url=link,
                                    unsubscribe_url=unsub,
                                ),
                                headers=headers,
                            )
                            if result.get("sent"):
                                any_sent = True
                        if any_sent:
                            await db.workspaces.update_one(
                                {"workspace_id": wid},
                                {"$set": {
                                    "trial_reminder_sent": True,
                                    "trial_reminder_sent_at": now.isoformat(),
                                }},
                            )
                            stats["trial_sent"] += 1
                        else:
                            stats["trial_skipped"] += 1

            if inactivity_nudge_due(ws, now=now):
                if not bullets or not emails:
                    stats["inactivity_skipped"] += 1
                else:
                    sendable = await ec.filter_unsuppressed(db, emails) if secret else list(emails)
                    if not sendable:
                        stats["suppressed_skipped"] += 1
                        stats["inactivity_skipped"] += 1
                    else:
                        days = days_inactive(ws, now=now)
                        any_sent = False
                        for addr in sendable:
                            unsub = (
                                ec.unsubscribe_url(app_base_url, addr, secret=secret)
                                if secret else ""
                            )
                            headers = {}
                            if secret and api_base:
                                one_click = ec.api_unsubscribe_url(api_base, addr, secret=secret)
                                headers = ec.list_unsubscribe_headers(one_click)
                            result = await send_email(
                                addr,
                                f"Your last briefing was {days} days ago. Here's what's changed since",
                                inactivity_email_html(
                                    workspace_name=name,
                                    days=days,
                                    bullets=bullets,
                                    briefing_url=link,
                                    unsubscribe_url=unsub,
                                ),
                                headers=headers,
                            )
                            if result.get("sent"):
                                any_sent = True
                        if any_sent:
                            await db.workspaces.update_one(
                                {"workspace_id": wid},
                                {"$set": {"inactivity_nudge_sent_at": now.isoformat()}},
                            )
                            stats["inactivity_sent"] += 1
                        else:
                            stats["inactivity_skipped"] += 1
        except Exception:
            logger.exception("retention check failed for workspace %s", wid)
            continue

    return stats
