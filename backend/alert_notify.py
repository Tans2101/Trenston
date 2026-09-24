"""Best-effort high-severity alert notifications (email + optional Slack)."""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def signal_notify_key(signal: dict) -> str:
    """Stable fingerprint for debounce across regenerations."""
    t = signal.get("type") or "unknown"
    rid = signal.get("related_id")
    if rid is not None and str(rid).strip():
        return f"{t}:{rid}"
    return f"{t}:{(signal.get('summary') or '').strip()}"


def high_severity_suggestions(suggestions: list) -> list:
    out = []
    for s in suggestions or []:
        sig = s.get("signal") or {}
        sev = (s.get("severity") or sig.get("severity") or "").lower()
        if sev == "high":
            out.append(s)
    return out


def new_high_alerts(suggestions: list, notified_ids: set) -> list:
    """Return high-severity suggestions not yet notified (open/undismissed debounce)."""
    fresh = []
    for s in high_severity_suggestions(suggestions):
        key = signal_notify_key(s.get("signal") or s)
        if key not in notified_ids:
            fresh.append(s)
    return fresh


def build_alert_email_html(workspace_name: str, alerts: list, app_url: str) -> str:
    items = "".join(
        f"<li style='margin:0 0 10px 0;'><b style='color:#fff;'>{_esc(a.get('title') or (a.get('signal') or {}).get('summary') or 'Alert')}</b>"
        f"<br><span style='color:#a1a1aa;'>{_esc(a.get('description') or (a.get('signal') or {}).get('detail') or '')}</span></li>"
        for a in alerts
    )
    link = (app_url or "").rstrip("/") + "/app/decisions"
    return f"""<!DOCTYPE html><html><body style="margin:0;background:#09090b;font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#09090b;padding:32px 16px;"><tr><td align="center">
<table width="560" cellpadding="0" cellspacing="0" style="background:#141417;border:1px solid rgba(255,255,255,0.08);border-radius:12px;">
<tr><td style="padding:28px 32px;">
<p style="color:#c9a962;font-size:11px;letter-spacing:2px;text-transform:uppercase;margin:0;">High-severity alert</p>
<h1 style="color:#ffffff;font-size:22px;font-weight:400;margin:10px 0 0 0;">{_esc(workspace_name)}</h1>
<p style="color:#a1a1aa;font-size:14px;line-height:1.6;margin:14px 0 0 0;">Trenston detected {len(alerts)} high-severity signal{"s" if len(alerts) != 1 else ""} that need your attention:</p>
<ul style="color:#a1a1aa;font-size:14px;line-height:1.5;margin:18px 0 0 0;padding-left:18px;">{items}</ul>
<table cellpadding="0" cellspacing="0" style="margin:28px 0 8px 0;"><tr>
<td style="background:#c9a962;border-radius:8px;">
<a href="{link}" style="display:inline-block;padding:12px 26px;color:#09090b;font-size:14px;font-weight:600;text-decoration:none;">Open Decisions in Trenston &rarr;</a>
</td></tr></table>
</td></tr></table>
</td></tr></table></body></html>"""


def _slack_escape(s: Any) -> str:
    """Escape Slack mrkdwn special chars (& < >). Plain @channel text is left as-is."""
    return (
        str(s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def build_slack_text(workspace_name: str, alerts: list, app_url: str) -> str:
    lines = [f"*Trenston high-severity alert: {_slack_escape(workspace_name)}*"]
    for a in alerts:
        title = a.get("title") or (a.get("signal") or {}).get("summary") or "Alert"
        detail = a.get("description") or (a.get("signal") or {}).get("detail") or ""
        lines.append(f"• {_slack_escape(title)}: {_slack_escape(detail)}")
    link = (app_url or "").rstrip("/") + "/app/decisions"
    lines.append(f"Open: {link}")
    return "\n".join(lines)


def _esc(s: Any) -> str:
    return (
        str(s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
