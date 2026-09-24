"""Shared ops briefing assembly for /briefing cards and the daily morning email.

Single source of truth for Sales / Procurement / Production / Maintenance
rollups — both the Briefing page and run_daily_briefing_cron call
`assemble_ops_briefing_data`. Missing targets/budgets/logs surface as
explicit "not set" / "no data", never fabricated zeros.
"""
from __future__ import annotations

import html
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import decision_engine
import department_migrate as dept_migrate
import departments_catalog as dept_catalog
import maintenance_ops as maint_ops
import procurement_metrics as proc_metrics
import procurement_spend as proc_spend
import production_daily_logs as prod_daily
import sales_order_book as sales_ob
import tz_utils

logger = logging.getLogger(__name__)


def _fmt_days(value: Optional[float]) -> str:
    if value is None:
        return "Not tracked"
    n = float(value)
    if n == int(n):
        return f"{int(n)}d"
    return f"{n:.1f}d"


def _money(n: Any) -> str:
    try:
        return f"${float(n):,.0f}"
    except (TypeError, ValueError):
        return "$0"


async def assemble_ops_briefing_data(db, workspace_id: str) -> dict:
    """Gather structured ops snapshot for one workspace.

    Returns sections keyed by department type (None when that department is
    not enabled). `has_content` is True when at least one ops department is
    enabled — empty metrics still render as explicit not-set / no-data lines.
    """
    depts = await dept_migrate.get_enabled_departments_by_type(
        db,
        workspace_id,
        (
            dept_catalog.TYPE_PROCUREMENT,
            dept_catalog.TYPE_PRODUCTION,
            dept_catalog.TYPE_SALES,
            dept_catalog.TYPE_ENGINEERING_MAINTENANCE,
        ),
    )
    ws_tz = await db.workspaces.find_one(
        {"workspace_id": workspace_id}, {"_id": 0, "timezone": 1},
    )
    local_today = tz_utils.workspace_today(ws_tz)
    month = sales_ob.current_month(local_today)
    sections: dict[str, Optional[dict]] = {
        "sales": None,
        "procurement": None,
        "production": None,
        "maintenance": None,
    }

    proc_dept = depts.get(dept_catalog.TYPE_PROCUREMENT)
    if proc_dept:
        try:
            rows = await db.procurement_requests.find(
                {"department_id": proc_dept["department_id"]},
                {
                    "_id": 0, "id": 1, "item": 1, "vendor_name": 1, "status": 1, "priority": 1,
                    "created_at": 1, "vendor_selected_at": 1, "ordered_at": 1, "updated_at": 1,
                    "expected_delivery_date": 1, "actual_delivery_date": 1, "cost": 1,
                },
            ).to_list(2000)
            lead = proc_metrics.department_lead_time_summary(rows, today=local_today)
            month_start, month_end = decision_engine.month_period_bounds()
            spend = proc_spend.spend_rollup(
                rows,
                period_start=month_start,
                period_end=month_end,
                budget=proc_dept.get("monthly_budget"),
                budget_entered=bool(proc_dept.get("monthly_budget_entered")),
            )
            sections["procurement"] = {
                "lead_time": lead,
                "spend": spend,
                "enabled": True,
            }
        except Exception:
            logger.exception("ops briefing: procurement section failed for workspace %s", workspace_id)
            sections["procurement"] = None

    prod_dept = depts.get(dept_catalog.TYPE_PRODUCTION)
    if prod_dept:
        try:
            orders = await db.production_work_orders.find(
                {"department_id": prod_dept["department_id"]},
                {
                    "_id": 0, "id": 1, "status": 1, "expected_yield_pct": 1, "unit": 1,
                    "reference": 1, "yield_tracking_enabled": 1,
                },
            ).to_list(1000)
            wo_ids = [o["id"] for o in orders if o.get("id")]
            logs_by_wo: dict[str, list] = {wid: [] for wid in wo_ids}
            today = local_today.isoformat()
            week_ago = (local_today - timedelta(days=7)).isoformat()
            if wo_ids:
                log_rows = await db.production_daily_logs.find(
                    {
                        "workspace_id": workspace_id,
                        "work_order_id": {"$in": wo_ids},
                        "date": {"$gte": week_ago},
                    },
                    {"_id": 0},
                ).to_list(5000)
                for log in log_rows:
                    logs_by_wo.setdefault(log.get("work_order_id"), []).append(log)
            day_summary = prod_daily.department_day_summary(orders, logs_by_wo, day=today)
            week_logs = [log for logs in logs_by_wo.values() for log in logs]
            ot = prod_daily.period_overtime_rollup(week_logs)

            yield_below: list[dict] = []
            for wo in orders:
                if (wo.get("status") or "") == "completed":
                    continue
                if not bool(wo.get("yield_tracking_enabled")):
                    continue
                expected = wo.get("expected_yield_pct")
                if expected is None:
                    continue
                logs = logs_by_wo.get(wo.get("id")) or []
                rollup = prod_daily.rollup_work_order_logs(
                    logs,
                    yield_tracking_enabled=True,
                    expected_yield_pct=expected,
                )
                if (rollup.get("yield_below_benchmark_days") or 0) > 0:
                    yield_below.append({
                        "work_order_id": wo.get("id"),
                        "reference": wo.get("reference") or wo.get("id"),
                        "below_days": rollup["yield_below_benchmark_days"],
                        "avg_actual_yield_pct": rollup.get("avg_actual_yield_pct"),
                        "expected_yield_pct": expected,
                    })

            sections["production"] = {
                "day_summary": day_summary,
                "overtime": ot,
                "yield_below_benchmark": yield_below,
                "yield_below_count": len(yield_below),
                "enabled": True,
            }
        except Exception:
            logger.exception("ops briefing: production section failed for workspace %s", workspace_id)
            sections["production"] = None

    sales_dept = depts.get(dept_catalog.TYPE_SALES)
    if sales_dept:
        try:
            entries = await db.sales_order_book.find(
                {"department_id": sales_dept["department_id"]},
                {"_id": 0},
            ).to_list(5000)
            # Settled: actual = confirmed order-book only. Never read deals.
            summary = sales_ob.order_book_summary(entries, month=month)
            target_row = await db.sales_targets.find_one(
                {"workspace_id": workspace_id, "month": month}, {"_id": 0},
            )
            tvs = sales_ob.target_vs_actual(
                target_row=target_row,
                confirmed_actual=summary["confirmed_this_month"],
            )
            sections["sales"] = {
                "summary": summary,
                "target_vs_actual": tvs,
                "month": month,
                "enabled": True,
            }
        except Exception:
            logger.exception("ops briefing: sales section failed for workspace %s", workspace_id)
            sections["sales"] = None

    maint_dept = depts.get(dept_catalog.TYPE_ENGINEERING_MAINTENANCE)
    if maint_dept:
        try:
            spare_rows = await db.maintenance_spares.find(
                {"department_id": maint_dept["department_id"]}, {"_id": 0},
            ).to_list(2000)
            below = maint_ops.spares_below_threshold(spare_rows)
            sched_rows = await db.maintenance_schedules.find(
                {"department_id": maint_dept["department_id"]}, {"_id": 0},
            ).to_list(2000)
            overdue = maint_ops.overdue_schedules(sched_rows, today=local_today)
            contract_rows = await db.maintenance_contracts.find(
                {"department_id": maint_dept["department_id"]}, {"_id": 0},
            ).to_list(2000)
            renewals = maint_ops.contracts_needing_attention(contract_rows, today=local_today)
            month_start, month_end = decision_engine.month_period_bounds()
            resolved = await db.maintenance_tickets.find(
                {
                    "department_id": maint_dept["department_id"],
                    "status": "resolved",
                    "$or": [
                        {"resolved_at": {"$gte": month_start.isoformat(), "$lt": month_end.isoformat()}},
                        {
                            "resolved_at": {"$exists": False},
                            "updated_at": {"$gte": month_start.isoformat(), "$lt": month_end.isoformat()},
                        },
                    ],
                },
                {"_id": 0, "cost": 1},
            ).to_list(5000)
            ticket_costs = []
            for t in resolved:
                if t.get("cost") is None:
                    continue
                try:
                    ticket_costs.append(float(t["cost"]))
                except (TypeError, ValueError):
                    pass
            ledger = await db.maintenance_costs.find(
                {"department_id": maint_dept["department_id"], "month": month_start.strftime("%Y-%m")},
                {"_id": 0, "amount": 1},
            ).to_list(2000)
            ledger_costs = []
            for row in ledger:
                try:
                    ledger_costs.append(float(row.get("amount") or 0))
                except (TypeError, ValueError):
                    pass
            overhead = maint_ops.overhead_rollup(
                ticket_costs=ticket_costs,
                ledger_costs=ledger_costs,
                budget=maint_dept.get("monthly_budget"),
                budget_entered=bool(maint_dept.get("monthly_budget_entered")),
            )
            overhead["period"] = month_start.strftime("%Y-%m")
            overhead["period_label"] = month_start.strftime("%B %Y")
            sections["maintenance"] = {
                "spares_below_threshold_count": len(below),
                "spares_below_threshold": below[:20],
                "overdue_schedules_count": len(overdue),
                "overdue_schedules": overdue[:20],
                "contracts_needing_renewal_count": len(renewals),
                "contracts_needing_renewal": renewals[:20],
                "overhead": overhead,
                "enabled": True,
            }
        except Exception:
            logger.exception("ops briefing: maintenance section failed for workspace %s", workspace_id)
            sections["maintenance"] = None

    enabled = [k for k, v in sections.items() if v is not None]
    return {
        "workspace_id": workspace_id,
        "month": month,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sections": sections,
        "enabled_departments": enabled,
        "has_content": bool(enabled),
    }


def ops_briefing_metric_cards(data: dict) -> list[dict]:
    """Map assemble_ops_briefing_data → Briefing page metric cards."""
    out: list[dict] = []
    sections = data.get("sections") or {}

    def _stamp(section: str, start: int) -> None:
        for card in out[start:]:
            card["section"] = section

    proc = sections.get("procurement")
    if proc:
        start = len(out)
        lead = proc["lead_time"]
        sourcing_known = lead["sourcing_sample_count"] > 0
        delay_known = lead["delay_sample_count"] > 0
        late_n = int(lead["currently_late_count"] or 0)
        out.append({
            "label": "Avg sourcing",
            "value": _fmt_days(lead["avg_sourcing_days"]) if sourcing_known else "Not tracked",
            "delta": 0,
            "tone": "neutral",
            "missing": not sourcing_known,
            "href": None if sourcing_known else "/app/departments/procurement",
        })
        out.append({
            "label": "Avg fulfillment delay",
            "value": _fmt_days(lead["avg_fulfillment_delay_days"]) if delay_known else "Not tracked",
            "delta": 0,
            "tone": "warning" if delay_known and (lead["avg_fulfillment_delay_days"] or 0) > 0 else ("positive" if delay_known else "neutral"),
            "missing": not delay_known,
            "href": None if delay_known else "/app/departments/procurement",
        })
        out.append({
            "label": "Late orders",
            "value": str(late_n),
            "delta": 0,
            "tone": "negative" if late_n else "positive",
            "missing": False,
            "href": "/app/departments/procurement" if late_n else None,
        })
        spend = proc["spend"]
        if spend["budget_entered"]:
            gap = spend.get("gap") or 0
            out.append({
                "label": "Procurement spend",
                "value": f"{_money(spend['actual'])} / {_money(spend['budget'])}",
                "delta": 0,
                "tone": "negative" if gap > 0 else "positive",
                "missing": False,
                "href": "/app/departments/procurement",
            })
        else:
            out.append({
                "label": "Procurement spend",
                "value": _money(spend["actual"]),
                "delta": 0,
                "tone": "neutral",
                "missing": spend["priced_count"] == 0,
                "href": "/app/departments/procurement",
            })
        _stamp("procurement", start)

    prod = sections.get("production")
    if prod:
        start = len(out)
        day_summary = prod["day_summary"]
        ot = prod["overtime"]
        if day_summary.get("has_data"):
            if day_summary.get("mixed_units"):
                parts = []
                for row in day_summary.get("by_unit") or []:
                    u = row.get("unit") or ""
                    a = row.get("total_actual")
                    t = row.get("total_target")
                    if a is not None and t is not None:
                        parts.append(f"{a:g}/{t:g}{(' ' + u) if u else ''}")
                value = " · ".join(parts) if parts else "Mixed units"
                tone = "negative" if any(
                    (r.get("shortfall") or 0) > 0 for r in (day_summary.get("by_unit") or [])
                ) else "positive"
            else:
                t = day_summary.get("total_target")
                a = day_summary.get("total_actual")
                u = day_summary.get("unit") or ""
                suffix = f" {u}" if u else ""
                value = f"{a:g} / {t:g}{suffix}" if t is not None and a is not None else (
                    f"{a:g}{suffix} logged" if a is not None else "Logged"
                )
                shortfall = day_summary.get("shortfall")
                tone = "negative" if shortfall is not None and shortfall > 0 else "positive"
            out.append({
                "label": "Today's output",
                "value": value,
                "delta": 0,
                "tone": tone,
                "missing": False,
                "href": "/app/departments/production",
            })
        else:
            out.append({
                "label": "Today's output",
                "value": "No data logged",
                "delta": 0,
                "tone": "neutral",
                "missing": True,
                "href": "/app/departments/production",
            })
        if ot.get("has_data") and ot.get("overtime_cost") is not None:
            out.append({
                "label": "OT cost (7d)",
                "value": _money(ot["overtime_cost"]),
                "delta": 0,
                "tone": "warning" if ot["overtime_cost"] > 0 else "neutral",
                "missing": False,
                "href": "/app/departments/production",
            })
        elif ot.get("has_data") and ot.get("overtime_hours") is not None:
            out.append({
                "label": "OT hours (7d)",
                "value": f"{ot['overtime_hours']:g}h",
                "delta": 0,
                "tone": "warning" if ot["overtime_hours"] > 0 else "neutral",
                "missing": False,
                "href": "/app/departments/production",
            })
        else:
            out.append({
                "label": "OT cost (7d)",
                "value": "No data logged",
                "delta": 0,
                "tone": "neutral",
                "missing": True,
                "href": "/app/departments/production",
            })
        y_n = prod.get("yield_below_count") or 0
        out.append({
            "label": "Yield below benchmark",
            "value": str(y_n) if y_n else ("None" if day_summary.get("has_data") else "No data"),
            "delta": 0,
            "tone": "negative" if y_n else "neutral",
            "missing": not day_summary.get("has_data") and y_n == 0,
            "href": "/app/departments/production" if y_n else None,
        })
        _stamp("production", start)

    sales = sections.get("sales")
    if sales:
        start = len(out)
        tvs = sales["target_vs_actual"]
        summary = sales["summary"]
        if tvs["target_entered"]:
            out.append({
                "label": "Sales vs target",
                "value": f"{_money(tvs['actual'])} / {_money(tvs['target'])}",
                "delta": 0,
                "tone": "negative" if (tvs.get("gap") or 0) < 0 else "positive",
                "missing": False,
                "href": "/app/sales",
            })
        else:
            out.append({
                "label": "Sales confirmed",
                "value": (
                    f"{_money(tvs['actual'])} · no target set"
                    if summary["line_count"]
                    else "No target set"
                ),
                "delta": 0,
                "tone": "neutral",
                "missing": True,
                "href": "/app/sales",
            })
        fwd = summary["forward_pipeline"]
        fwd_total = sum(
            (b.get("expected") or 0) + (b.get("in_negotiation") or 0) + (b.get("confirmed") or 0)
            for b in fwd
        )
        out.append({
            "label": "Order book (3mo)",
            "value": _money(fwd_total) if summary["line_count"] else "No data",
            "delta": 0,
            "tone": "neutral",
            "missing": summary["line_count"] == 0,
            "href": "/app/sales",
        })
        _stamp("sales", start)

    maint = sections.get("maintenance")
    if maint:
        start = len(out)
        below_n = maint["spares_below_threshold_count"]
        overdue_n = maint["overdue_schedules_count"]
        renew_n = maint["contracts_needing_renewal_count"]
        out.append({
            "label": "Spares low",
            "value": str(below_n),
            "delta": 0,
            "tone": "negative" if below_n else "positive",
            "missing": False,
            "href": "/app/departments/engineering_maintenance" if below_n else None,
        })
        out.append({
            "label": "Maint overdue",
            "value": str(overdue_n),
            "delta": 0,
            "tone": "negative" if overdue_n else "positive",
            "missing": False,
            "href": "/app/departments/engineering_maintenance" if overdue_n else None,
        })
        out.append({
            "label": "AMC renewals",
            "value": str(renew_n),
            "delta": 0,
            "tone": "negative" if renew_n else "positive",
            "missing": False,
            "href": "/app/departments/engineering_maintenance" if renew_n else None,
        })
        overhead = maint["overhead"]
        if overhead["budget_entered"]:
            gap = overhead.get("gap") or 0
            out.append({
                "label": "Maint overhead",
                "value": f"{_money(overhead['actual'])} / {_money(overhead['budget'])}",
                "delta": 0,
                "tone": "negative" if gap > 0 else "positive",
                "missing": False,
                "href": "/app/departments/engineering_maintenance",
            })
        else:
            out.append({
                "label": "Maint overhead",
                "value": f"{_money(overhead['actual'])} · no budget set",
                "delta": 0,
                "tone": "neutral",
                "missing": overhead["actual"] == 0,
                "href": "/app/departments/engineering_maintenance",
            })
        _stamp("maintenance", start)

    return out


def _row(label: str, value: str) -> str:
    return (
        f'<tr><td style="padding:6px 0;color:#a1a1aa;font-size:13px;vertical-align:top;">'
        f"{html.escape(label)}</td>"
        f'<td style="padding:6px 0 6px 16px;color:#ffffff;font-size:13px;text-align:right;">'
        f"{html.escape(value)}</td></tr>"
    )


def _section(title: str, rows_html: str) -> str:
    return f"""\
<tr><td style="padding:22px 36px 0 36px;">
<p style="color:#c9a962;font-size:11px;letter-spacing:2px;text-transform:uppercase;margin:0 0 10px 0;">{html.escape(title)}</p>
<table width="100%" cellpadding="0" cellspacing="0">{rows_html}</table>
</td></tr>"""


def daily_briefing_email_html(
    *,
    workspace_name: str,
    data: dict,
    app_url: str,
    unsubscribe_url: str = "",
) -> str:
    """Plain scannable HTML morning briefing. Reuses weekly digest CAN-SPAM footer."""
    import email_compliance as ec

    name = html.escape(workspace_name or "your company")
    link = html.escape((app_url or "").rstrip("/") + "/app/briefing", quote=True)
    month = (data.get("month") or "").strip() or "this month"
    sections = data.get("sections") or {}
    blocks: list[str] = []

    sales = sections.get("sales")
    if sales:
        tvs = sales["target_vs_actual"]
        summary = sales["summary"]
        rows = []
        if tvs.get("target_entered"):
            gap = tvs.get("gap")
            gap_s = _money(gap) if gap is not None else "—"
            rows.append(_row("Target vs actual", f"{_money(tvs['actual'])} / {_money(tvs['target'])} (gap {gap_s})"))
        else:
            rows.append(_row("Monthly target", "Not set"))
            rows.append(_row(
                "Confirmed actual",
                _money(tvs.get("actual") or 0) if summary.get("line_count") else "No data",
            ))
        country_bits = summary.get("by_country_this_month") or []
        if country_bits:
            rows.append(_row(
                "By country (this month)",
                " · ".join(f"{c['country']} {_money(c['total_value'])}" for c in country_bits[:6]),
            ))
        else:
            rows.append(_row("By country (this month)", "No data"))
        product_bits = summary.get("by_product_this_month") or []
        if product_bits:
            rows.append(_row(
                "By product (this month)",
                " · ".join(f"{p['product']} {_money(p['total_value'])}" for p in product_bits[:6]),
            ))
        else:
            rows.append(_row("By product (this month)", "No data"))
        fwd_parts = []
        for b in summary.get("forward_pipeline") or []:
            exp = (b.get("expected") or 0) + (b.get("in_negotiation") or 0)
            fwd_parts.append(f"{b['month']} {_money(exp)}")
        rows.append(_row(
            "Forward pipeline (expected / in negotiation)",
            " · ".join(fwd_parts) if fwd_parts else "No data",
        ))
        blocks.append(_section("Sales", "".join(rows)))

    proc = sections.get("procurement")
    if proc:
        lead = proc["lead_time"]
        spend = proc["spend"]
        rows = []
        rows.append(_row(
            "Avg sourcing time",
            _fmt_days(lead["avg_sourcing_days"]) if lead["sourcing_sample_count"] else "Not tracked",
        ))
        rows.append(_row(
            "Avg fulfillment delay",
            _fmt_days(lead["avg_fulfillment_delay_days"]) if lead["delay_sample_count"] else "Not tracked",
        ))
        rows.append(_row("Currently late orders", str(int(lead["currently_late_count"] or 0))))
        if spend.get("budget_entered"):
            gap = spend.get("gap")
            rows.append(_row(
                "Spend vs budget",
                f"{_money(spend['actual'])} / {_money(spend['budget'])}"
                + (f" (gap {_money(gap)})" if gap is not None else ""),
            ))
        else:
            rows.append(_row("Spend this month", f"{_money(spend['actual'])} · no budget set"))
        rows.append(_row(
            "Unpriced requests",
            str(spend.get("unpriced_count") or 0)
            + (" (total may be incomplete)" if (spend.get("unpriced_count") or 0) else ""),
        ))
        vendors = spend.get("by_vendor") or []
        rows.append(_row(
            "By vendor",
            " · ".join(f"{v['vendor_name']} {_money(v['total'])}" for v in vendors[:5])
            if vendors else "No data",
        ))
        items = spend.get("by_item") or []
        rows.append(_row(
            "By item",
            " · ".join(f"{v['item']} {_money(v['total'])}" for v in items[:5])
            if items else "No data",
        ))
        blocks.append(_section("Procurement", "".join(rows)))

    prod = sections.get("production")
    if prod:
        day = prod["day_summary"]
        ot = prod["overtime"]
        rows = []
        if day.get("has_data"):
            if day.get("mixed_units"):
                parts = []
                for row in day.get("by_unit") or []:
                    u = row.get("unit") or ""
                    a = row.get("total_actual")
                    t = row.get("total_target")
                    if a is not None and t is not None:
                        parts.append(f"{a:g}/{t:g}{(' ' + u) if u else ''}")
                rows.append(_row("Today's output vs target", " · ".join(parts) if parts else "Mixed units"))
            else:
                t = day.get("total_target")
                a = day.get("total_actual")
                u = day.get("unit") or ""
                suffix = f" {u}" if u else ""
                if t is not None and a is not None:
                    rows.append(_row("Today's output vs target", f"{a:g} / {t:g}{suffix}"))
                elif a is not None:
                    rows.append(_row("Today's output vs target", f"{a:g}{suffix} logged · no target"))
                else:
                    rows.append(_row("Today's output vs target", "No data"))
        else:
            rows.append(_row("Today's output vs target", "No data logged"))
        if ot.get("has_data") and ot.get("overtime_cost") is not None:
            rows.append(_row("Overtime cost (7d)", _money(ot["overtime_cost"])))
        elif ot.get("has_data") and ot.get("overtime_hours") is not None:
            rows.append(_row("Overtime hours (7d)", f"{ot['overtime_hours']:g}h"))
        else:
            rows.append(_row("Overtime (7d)", "No data logged"))
        y_n = prod.get("yield_below_count") or 0
        if y_n:
            refs = ", ".join(
                (y.get("reference") or y.get("work_order_id") or "?")
                for y in (prod.get("yield_below_benchmark") or [])[:5]
            )
            rows.append(_row("Yield below benchmark", f"{y_n} work order(s): {refs}"))
        else:
            rows.append(_row("Yield below benchmark", "None" if day.get("has_data") else "No data"))
        blocks.append(_section("Production", "".join(rows)))

    maint = sections.get("maintenance")
    if maint:
        oh = maint["overhead"]
        rows = [
            _row("Spares below threshold", str(maint["spares_below_threshold_count"])),
            _row("Overdue schedules", str(maint["overdue_schedules_count"])),
            _row("AMCs needing renewal", str(maint["contracts_needing_renewal_count"])),
        ]
        if oh.get("budget_entered"):
            gap = oh.get("gap")
            rows.append(_row(
                "Overhead vs budget",
                f"{_money(oh['actual'])} / {_money(oh['budget'])}"
                + (f" (gap {_money(gap)})" if gap is not None else ""),
            ))
        else:
            rows.append(_row("Overhead this month", f"{_money(oh['actual'])} · no budget set"))
        blocks.append(_section("Engineering & Maintenance", "".join(rows)))

    body_sections = "\n".join(blocks) if blocks else _section(
        "Operations", _row("Status", "No Sales / Procurement / Production / Maintenance departments enabled"),
    )

    footer = (
        ec.marketing_footer_html(unsubscribe_url=unsubscribe_url)
        if unsubscribe_url
        else """\
<tr><td style="padding:20px 36px 30px 36px;border-top:1px solid rgba(255,255,255,0.06);">
<p style="color:#52525b;font-size:12px;margin:0;line-height:1.6;">Know what matters before your first meeting.</p>
</td></tr>"""
    )
    return f"""\
<!DOCTYPE html><html><body style="margin:0;padding:0;background:#09090b;font-family:'Helvetica Neue',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#09090b;padding:40px 0;">
<tr><td align="center">
<table width="520" cellpadding="0" cellspacing="0" style="background:#121214;border:1px solid rgba(255,255,255,0.08);border-radius:14px;overflow:hidden;">
<tr><td style="padding:32px 36px 8px 36px;">
<p style="color:#c9a962;font-size:11px;letter-spacing:2px;text-transform:uppercase;margin:0;">Daily briefing</p>
<h1 style="color:#ffffff;font-size:22px;font-weight:400;margin:10px 0 0 0;line-height:1.3;">Morning snapshot for<br><span style="color:#c9a962;">{name}</span></h1>
<p style="color:#a1a1aa;font-size:14px;line-height:1.6;margin:14px 0 0 0;">Operational numbers for {html.escape(month)}. Metrics with no data yet are labeled explicitly — never blank or invented.</p>
</td></tr>
{body_sections}
<tr><td style="padding:28px 36px 8px 36px;">
<table cellpadding="0" cellspacing="0"><tr>
<td style="background:#c9a962;border-radius:8px;">
<a href="{link}" style="display:inline-block;padding:12px 26px;color:#09090b;font-size:14px;font-weight:600;text-decoration:none;">Open Briefing in Trenston &rarr;</a>
</td></tr></table>
</td></tr>
{footer}
</table>
</td></tr></table></body></html>"""
