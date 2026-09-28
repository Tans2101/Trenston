"""Parse historical financial CSV uploads into preview rows (no DB writes).

Expected columns (case-insensitive): date|month, type, category, amount,
optional name|item|vendor, optional note|description|memo.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import datetime
from typing import Any, Optional

from finance_entry import normalize_entry_name


TYPE_ALIASES = {
    "revenue": "revenue",
    "income": "revenue",
    "sales": "revenue",
    "expense": "expense",
    "expenses": "expense",
    "cost": "expense",
    "costs": "expense",
}


def _norm_header(h: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (h or "").strip().lower())


HEADER_MAP = {
    "date": "date",
    "month": "date",
    "period": "date",
    "type": "type",
    "entrytype": "type",
    "category": "category",
    "cat": "category",
    "name": "name",
    "item": "name",
    "itemname": "name",
    "vendor": "name",
    "amount": "amount",
    "value": "amount",
    "amt": "amount",
    "note": "note",
    "notes": "note",
    "description": "note",
    "memo": "note",
}


def _parse_month(raw: str) -> Optional[str]:
    import finance_recurrence as fin_recur

    s = (raw or "").strip()
    if not s:
        return None
    # Prefer unambiguous ISO forms first
    if re.fullmatch(r"\d{4}-\d{2}", s):
        return s if fin_recur.is_valid_month(s) else None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        try:
            dt = datetime.strptime(s, "%Y-%m-%d")
            return dt.strftime("%Y-%m")
        except ValueError:
            return None
    if re.fullmatch(r"\d{4}/\d{2}/\d{2}", s):
        try:
            dt = datetime.strptime(s, "%Y/%m/%d")
            return dt.strftime("%Y-%m")
        except ValueError:
            return None
    # Ambiguous day/month numeric forms — reject rather than guess locale
    if re.fullmatch(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", s):
        parts = re.split(r"[/-]", s)
        try:
            a, b, y = int(parts[0]), int(parts[1]), int(parts[2])
            if y < 100:
                y += 2000
            # Only accept when one side must be the month (>12)
            if a > 12 and 1 <= b <= 12:
                dt = datetime(y, b, a)  # D/M/Y
                return dt.strftime("%Y-%m")
            if b > 12 and 1 <= a <= 12:
                dt = datetime(y, a, b)  # M/D/Y
                return dt.strftime("%Y-%m")
            # Both <= 12 — ambiguous
            return None
        except ValueError:
            return None
    for fmt in ("%Y-%m", "%b %Y", "%B %Y", "%m/%Y"):
        try:
            dt = datetime.strptime(s, fmt)
            out = dt.strftime("%Y-%m")
            return out if fin_recur.is_valid_month(out) else None
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        out = dt.strftime("%Y-%m")
        return out if fin_recur.is_valid_month(out) else None
    except ValueError:
        return None


def _parse_amount(raw: str) -> Optional[float]:
    s = (raw or "").strip()
    if not s:
        return None
    s = s.replace(",", "").replace(" ", "")
    # Strip common currency symbols / codes
    s = re.sub(r"^[^\d\-\+\(]+", "", s)
    s = s.replace("(", "-").replace(")", "")
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def _parse_type(raw: str) -> Optional[str]:
    key = (raw or "").strip().lower()
    return TYPE_ALIASES.get(key)


def parse_financial_csv(text: str, *, now=None) -> dict[str, Any]:
    """Return {valid: [...], skipped: [{row, reason}], parsed_row_count} without writing.

    ``now`` should be the workspace-local datetime so "future month" matches the
    founder's calendar (defaults to UTC)."""
    import finance_recurrence as fin_recur

    if text.startswith("\ufeff"):
        text = text[1:]
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        raise ValueError("CSV has no header row")

    col_map: dict[str, str] = {}
    for h in reader.fieldnames:
        key = HEADER_MAP.get(_norm_header(h))
        if key and key not in col_map:
            col_map[key] = h

    missing = [c for c in ("date", "type", "category", "amount") if c not in col_map]
    if missing:
        raise ValueError(
            f"Missing required column(s): {', '.join(missing)}. "
            "Expected date (or month), type, category, amount, and optional name/note."
        )

    valid = []
    skipped = []
    for i, row in enumerate(reader, start=2):  # 1-indexed file rows; header is 1
        raw_date = row.get(col_map["date"], "")
        raw_type = row.get(col_map["type"], "")
        raw_cat = row.get(col_map["category"], "")
        raw_amt = row.get(col_map["amount"], "")
        raw_name = row.get(col_map["name"], "") if "name" in col_map else ""
        raw_note = row.get(col_map["note"], "") if "note" in col_map else ""

        month = _parse_month(raw_date)
        if not month:
            skipped.append({"row": i, "reason": f"Invalid date/month: {raw_date!r}"})
            continue
        if fin_recur.is_future_month(month, now):
            skipped.append({"row": i, "reason": f"Month cannot be in the future: {month}"})
            continue
        entry_type = _parse_type(raw_type)
        if not entry_type:
            skipped.append({"row": i, "reason": f"Invalid type (want revenue/expense): {raw_type!r}"})
            continue
        amount = _parse_amount(raw_amt)
        if amount is None:
            skipped.append({"row": i, "reason": f"Invalid amount: {raw_amt!r}"})
            continue
        if amount < 0:
            skipped.append({"row": i, "reason": f"Amount must be non-negative: {raw_amt!r}"})
            continue
        category = (raw_cat or "").strip() or "Other"
        note = (raw_note or "").strip()
        valid.append({
            "type": entry_type,
            "category": category,
            "name": normalize_entry_name(raw_name, category),
            "amount": amount,
            "month": month,
            "note": note,
            "recurring": False,
            "source_row": i,
        })

    return {
        "valid": valid,
        "skipped": skipped,
        "parsed_row_count": len(valid) + len(skipped),
        "valid_count": len(valid),
        "skipped_count": len(skipped),
    }
