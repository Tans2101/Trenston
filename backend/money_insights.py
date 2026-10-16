"""What's making money, what's losing money, and why it matters.

Code does the arithmetic from the ledger; the AI only turns those facts into
plain sentences. Anything the AI writes that contains a figure we did not give
it is thrown away and replaced by the plain template below, so a wrong number
never reaches the page.

Revenue and expense lines come from the same expansion the Financials totals use
(finance_recurrence.line_items_for_period), so these sections always agree with
the rest of the page. Unknown is not zero: with no revenue or expense rows for the
period, the section says nothing was logged instead of describing a $0 month.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime
from typing import Any, Optional

import finance_recurrence as fin_recur
from money_fmt import fmt_money_plain as fmt_money

TOP_N = 5
SECTION_KEYS = ("making_money", "losing_money", "why_it_matters")
MAX_SECTION_CHARS = 700


def _signed(row: dict) -> float:
    amount = float(row.get("amount") or 0.0)
    return -abs(amount) if row.get("is_credit") else abs(amount)


def _by_category(rows: list[dict], entry_type: str) -> dict[str, float]:
    out: dict[str, float] = defaultdict(float)
    for r in rows:
        if r.get("type") == entry_type:
            out[(r.get("category") or "Other").strip() or "Other"] += _signed(r)
    return dict(out)


def _by_line(rows: list[dict], entry_type: str) -> dict[tuple[str, str], float]:
    out: dict[tuple[str, str], float] = defaultdict(float)
    for r in rows:
        if r.get("type") == entry_type:
            name = (r.get("name") or r.get("category") or "Other").strip() or "Other"
            cat = (r.get("category") or "Other").strip() or "Other"
            out[(name, cat)] += _signed(r)
    return dict(out)


def _pct_change(cur: float, prev: float) -> Optional[int]:
    if prev and prev > 0:
        return int(round((cur - prev) / prev * 100))
    return None


def _side(rows_now: list[dict], rows_prev: list[dict], entry_type: str, currency: str) -> dict[str, Any]:
    cats = _by_category(rows_now, entry_type)
    prev = _by_category(rows_prev, entry_type)
    total = sum(cats.values())
    ranked = sorted(cats.items(), key=lambda kv: kv[1], reverse=True)[:TOP_N]
    by_category = []
    for cat, amt in ranked:
        row = {"category": cat, "amount": fmt_money(amt, currency)}
        pct = _pct_change(amt, prev.get(cat, 0.0))
        if pct is not None:
            row["change_vs_previous_month_pct"] = pct
        elif cat not in prev:
            row["new_this_month"] = True
        by_category.append(row)
    lines = sorted(_by_line(rows_now, entry_type).items(), key=lambda kv: kv[1], reverse=True)[:TOP_N]
    top_lines = [
        {"name": name, "category": cat, "amount": fmt_money(amt, currency)}
        for (name, cat), amt in lines
    ]
    moves = []
    for cat in set(cats) | set(prev):
        delta = cats.get(cat, 0.0) - prev.get(cat, 0.0)
        if abs(delta) >= 1:
            moves.append((cat, delta))
    moves.sort(key=lambda kv: kv[1], reverse=True)
    biggest_up = [
        {"category": c, "increase": fmt_money(d, currency)} for c, d in moves[:3] if d > 0
    ]
    biggest_down = [
        {"category": c, "decrease": fmt_money(-d, currency)} for c, d in reversed(moves[-3:]) if d < 0
    ]
    return {
        "has_data": bool(cats),
        "total": fmt_money(total, currency),
        "total_value": total,
        "by_category": by_category,
        "top_lines": top_lines,
        "biggest_increases": biggest_up,
        "biggest_decreases": biggest_down,
    }


def build_facts(
    entries: list[dict],
    *,
    current_month: str,
    horizon: str,
    currency: str = "usd",
) -> dict[str, Any]:
    """Facts for the latest finished month (or this month so far if that is all there is)."""
    valid = [e for e in entries or [] if fin_recur.is_valid_month(str(e.get("month") or ""))]
    last_full = fin_recur.month_add(current_month, -1)
    has_history = any(str(e["month"]) <= last_full for e in valid)
    period = last_full if has_history else current_month
    previous = fin_recur.month_add(period, -1)
    rows_now = fin_recur.line_items_for_period(valid, period, horizon)
    rows_prev = fin_recur.line_items_for_period(valid, previous, horizon)
    revenue = _side(rows_now, rows_prev, "revenue", currency)
    expenses = _side(rows_now, rows_prev, "expense", currency)
    net = revenue["total_value"] - expenses["total_value"]
    label = datetime.strptime(period, "%Y-%m").strftime("%B %Y")
    return {
        "period": period,
        "period_label": label,
        "month_so_far": period == current_month,
        "currency": currency,
        "has_data": revenue["has_data"] or expenses["has_data"],
        "revenue": revenue,
        "expenses": expenses,
        "net": fmt_money(abs(net), currency),
        "net_direction": "profit" if net > 0 else ("loss" if net < 0 else "breakeven"),
    }


def _strip_values(facts: dict) -> dict:
    out = json.loads(json.dumps(facts, default=str))
    for side in ("revenue", "expenses"):
        out[side].pop("total_value", None)
    return out


def context_hash(context: dict) -> str:
    blob = json.dumps(context, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:24]


# ---------------------------------------------------------------- plain template


def _cat_phrase(row: dict) -> str:
    text = f"{row['category']} at {row['amount']}"
    pct = row.get("change_vs_previous_month_pct")
    if pct is not None and pct != 0:
        text += f", {'up' if pct > 0 else 'down'} {abs(pct)}% from the month before"
    elif row.get("new_this_month"):
        text += ", new this month"
    return text


def template_sections(facts: dict, runway: Optional[dict] = None) -> dict[str, str]:
    """Plain, no-AI wording. Used for empty data and whenever AI output fails the figure check."""
    label = facts["period_label"] + (" so far" if facts.get("month_so_far") else "")
    rev, exp = facts["revenue"], facts["expenses"]

    if not rev["has_data"]:
        making = f"No revenue is logged for {label}. Add your sales or subscriptions to see what earns money."
    else:
        making = f"In {label}, revenue was {rev['total']}. Biggest source: {_cat_phrase(rev['by_category'][0])}."
        if len(rev["by_category"]) > 1:
            making += f" Next: {_cat_phrase(rev['by_category'][1])}."

    if not exp["has_data"]:
        losing = f"No expenses are logged for {label}. Add your costs to see where money goes."
    else:
        losing = f"In {label}, expenses were {exp['total']}. Biggest cost: {_cat_phrase(exp['by_category'][0])}."
        if exp["biggest_increases"]:
            up = exp["biggest_increases"][0]
            losing += f" Fastest growing: {up['category']}, up {up['increase']}."

    if not facts["has_data"]:
        why = "Once revenue and expenses are logged, this explains what they mean for your cash."
    else:
        direction = facts["net_direction"]
        if direction == "profit":
            why = f"You made a profit of {facts['net']} in {label}."
        elif direction == "loss":
            why = f"You lost {facts['net']} in {label}."
        else:
            why = f"You broke even in {label}."
        months = (runway or {}).get("runway_months")
        basis = (runway or {}).get("runway_basis")
        if months is not None and (runway or {}).get("cash_entered"):
            why += f" Runway is {months} months{f', {basis}' if basis else ''}."
        elif (runway or {}).get("cash_entered") is False:
            why += " Add your cash balance on this page to see how long it lasts."
    return {"making_money": making, "losing_money": losing, "why_it_matters": why}


# ---------------------------------------------------------------- AI wording

SYSTEM_PROMPT = (
    "You write three short notes for a company owner from facts about last month's money. "
    "Return ONLY a JSON object with exactly these string keys: making_money, losing_money, why_it_matters. "
    "making_money: what earns the money, using revenue.by_category and revenue.top_lines. "
    "losing_money: where the money goes, using expenses.by_category, expenses.top_lines and expenses.biggest_increases. "
    "why_it_matters: what the result means for the business and one concrete thing to do next. "
    "Each note is 2 or 3 short sentences, under 25 words each, plain English, like a thoughtful person talking. "
    "Only use figures that appear literally in the data. Never calculate, round, or invent a number. "
    "Revenue and expenses are not profit per product, so do not say a product or customer is profitable. "
    "If a side has_data false, say plainly that nothing is logged and what to add. Never treat missing data as zero. "
    "If runway is given, quote runway_months exactly and mention runway_basis. "
    "No bullet points, no bold, no em dashes. Do not use the words 'synthesis', 'signal', or 'leverage'."
)

_FIGURE_RE = re.compile(r"[$₱€£₹]?\d(?:[\d,]*\d)?(?:\.\d+)?%?")


def _figures_grounded(text: str, context_blob: str) -> bool:
    for tok in _FIGURE_RE.findall(text):
        digits = re.sub(r"\D", "", tok)
        if len(digits) < 2:
            continue
        if tok.endswith("%"):
            # Percent changes are stored as plain numbers (sign says up or down).
            if not re.search(rf'pct":\s*-?{re.escape(tok[:-1])}\b', context_blob):
                return False
        elif tok not in context_blob and tok.lstrip("$₱€£₹") not in context_blob:
            return False
    return True


def parse_sections(raw: str, context_blob: str) -> Optional[dict[str, str]]:
    """Return the AI sections only if they are well formed and every figure is grounded."""
    cleaned = (raw or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    out: dict[str, str] = {}
    for key in SECTION_KEYS:
        val = data.get(key)
        if not isinstance(val, str) or not val.strip():
            return None
        val = val.strip()[:MAX_SECTION_CHARS]
        if not _figures_grounded(val, context_blob):
            return None
        out[key] = val
    return out
