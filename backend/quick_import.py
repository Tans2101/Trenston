"""Quick import: turn the spreadsheets a company already has into Trenston records.

Pure functions only (no database). The flow is:

  read_workbook(bytes)        -> sheets: [{name, grid}]
  analyze_sheet(sheet)        -> heuristic plan: {kind, header_row, columns, ...}
  merge_ai_plan(plan, ai)     -> plan with the AI's column mapping, validated
  build_records(sheet, plan)  -> {records, skipped, notes}
  clean_record(kind, record)  -> validated record ready to insert (confirm step)

Trust rule: the AI (when used) only decides which column means what, and
whether a P&L line is revenue or expense. Every value that lands in Trenston
is read from the file by this module and validated again on confirm.
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from typing import Any, Optional

MAX_BYTES = 5 * 1024 * 1024
MAX_SHEETS = 10
MAX_ROWS_PER_SHEET = 5000
MAX_COLS = 60
SAMPLE_ROWS = 8
MAX_TEXT = 200

KIND_FINANCIAL = "financial"            # one row per money entry
KIND_FINANCIAL_WIDE = "financial_wide"  # P&L / budget: lines down, months across
KIND_DEALS = "deals"
KIND_TASKS = "tasks"
KIND_PRODUCTION = "production"
KIND_PROCUREMENT = "procurement"
KIND_SKIP = "skip"

IMPORTABLE_KINDS = (
    KIND_FINANCIAL, KIND_FINANCIAL_WIDE, KIND_DEALS, KIND_TASKS,
    KIND_PRODUCTION, KIND_PROCUREMENT,
)
ALL_KINDS = IMPORTABLE_KINDS + (KIND_SKIP,)

# What each kind becomes in Trenston (record kind used on confirm).
RECORD_KIND = {
    KIND_FINANCIAL: "financial",
    KIND_FINANCIAL_WIDE: "financial",
    KIND_DEALS: "deal",
    KIND_TASKS: "task",
    KIND_PRODUCTION: "work_order",
    KIND_PROCUREMENT: "purchase_request",
}

KIND_LABEL = {
    KIND_FINANCIAL: "Money in and out",
    KIND_FINANCIAL_WIDE: "Monthly P&L or budget",
    KIND_DEALS: "Sales deals",
    KIND_TASKS: "Tasks",
    KIND_PRODUCTION: "Production orders",
    KIND_PROCUREMENT: "Purchase requests",
    KIND_SKIP: "Not imported",
}

# Department each kind needs switched on (None = always available).
KIND_DEPARTMENT = {
    KIND_FINANCIAL: None,
    KIND_FINANCIAL_WIDE: None,
    KIND_DEALS: None,
    KIND_TASKS: None,
    KIND_PRODUCTION: "production",
    KIND_PROCUREMENT: "procurement",
}

# Field -> header synonyms (normalized: lowercase letters and digits only).
FIELDS: dict[str, dict[str, list[str]]] = {
    KIND_FINANCIAL: {
        "date": ["date", "month", "period", "transactiondate", "txndate", "postingdate", "valuedate", "invoicedate"],
        "amount": ["amount", "value", "amt", "total", "net", "sum", "php", "usd", "amountphp", "amountusd"],
        "money_in": ["moneyin", "in", "credit", "credits", "deposit", "deposits", "received", "income", "inflow"],
        "money_out": ["moneyout", "out", "debit", "debits", "withdrawal", "withdrawals", "paid", "spent", "outflow", "payment", "payments"],
        "type": ["type", "entrytype", "kind", "incomeexpense", "revenueexpense", "inout"],
        "category": ["category", "cat", "account", "accountname", "glaccount", "class", "group"],
        "name": ["name", "description", "item", "details", "particulars", "payee", "vendor", "customer", "memo", "narration", "reference"],
    },
    KIND_DEALS: {
        "name": ["deal", "dealname", "opportunity", "project", "name", "title", "client", "customer", "company", "account", "lead"],
        "company": ["company", "client", "customer", "account", "organization", "organisation", "business"],
        "value": ["value", "amount", "dealvalue", "dealsize", "price", "revenue", "contractvalue", "estimatedvalue", "quote", "quotedamount", "total"],
        "stage": ["stage", "status", "pipelinestage", "dealstage", "phase"],
        "owner_name": ["owner", "salesperson", "rep", "salesrep", "accountmanager", "assignedto", "handledby"],
        "close_date": ["closedate", "expectedclose", "closingdate", "expectedclosedate", "closedon", "datewon"],
        "next_step": ["nextstep", "nextaction", "followup", "notes", "note", "comments", "remarks"],
    },
    KIND_TASKS: {
        "title": ["task", "title", "todo", "action", "actionitem", "item", "description", "activity", "name"],
        "priority": ["priority", "urgency", "importance"],
        "due": ["due", "duedate", "deadline", "dueon", "targetdate", "by", "enddate"],
        "status": ["status", "state", "progress", "done", "completed", "stage"],
        "tag": ["tag", "category", "area", "project", "department", "team", "label"],
    },
    KIND_PRODUCTION: {
        "reference": ["joborder", "jobno", "jobnumber", "job", "workorder", "wo", "wono", "orderno", "ordernumber", "jo", "jono", "batch", "batchno", "reference", "ref", "lot", "lotno"],
        "product": ["product", "item", "sku", "productname", "model", "description", "style"],
        "quantity_planned": ["quantity", "qty", "units", "pcs", "quantityplanned", "plannedqty", "targetqty", "orderqty", "volume"],
        "customer": ["customer", "client", "buyer", "account"],
        "due_date": ["due", "duedate", "deliverydate", "deadline", "shipdate", "targetdate", "etd"],
        "priority": ["priority", "urgency"],
        "notes": ["notes", "note", "remarks", "comments", "status"],
    },
    KIND_PROCUREMENT: {
        "item": ["item", "material", "materials", "part", "partname", "description", "product", "rawmaterial", "itemname", "goods"],
        "quantity": ["quantity", "qty", "units", "pcs", "orderqty", "quantityordered", "volume"],
        "vendor_name": ["vendor", "supplier", "seller", "vendorname", "suppliername", "source"],
        "cost": ["cost", "price", "amount", "totalcost", "unitcost", "value", "total", "pototal"],
        "expected_delivery_date": ["delivery", "deliverydate", "eta", "expecteddelivery", "expecteddate", "arrival", "duedate"],
        "priority": ["priority", "urgency"],
        "notes": ["notes", "note", "remarks", "comments", "po", "pono", "ponumber"],
    },
}

REQUIRED = {
    KIND_FINANCIAL: ("date",),          # plus amount or money_in/money_out
    KIND_DEALS: ("name",),
    KIND_TASKS: ("title",),
    KIND_PRODUCTION: ("reference",),
    KIND_PROCUREMENT: ("item",),
}

# Words that only make sense for one kind; they decide close calls.
KIND_SIGNALS = {
    KIND_FINANCIAL: ["debit", "credit", "moneyin", "moneyout", "withdrawal", "deposit", "income", "expense", "account", "category", "particulars"],
    KIND_DEALS: ["stage", "pipeline", "deal", "opportunity", "lead", "closedate", "salesperson", "rep", "prospect"],
    KIND_TASKS: ["task", "todo", "assignee", "assignedto", "deadline", "due", "duedate"],
    KIND_PRODUCTION: ["joborder", "workorder", "wo", "batch", "lot", "sku", "produced", "output", "line", "shift"],
    KIND_PROCUREMENT: ["supplier", "vendor", "material", "rawmaterial", "eta", "po", "pono", "ponumber", "purchase"],
}

_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9, "oct": 10,
    "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}

# P&L lines that are summaries, not entries. Importing them would double count.
_SUMMARY_LINE_RE = re.compile(
    r"\b(total|subtotal|sub-total|net|gross\s+profit|gross\s+margin|operating\s+(profit|income)|"
    r"ebitda|ebit|profit|loss|margin|balance|opening|closing|beginning|ending|cash\s+(at|on\s+hand)|"
    r"surplus|deficit|variance|cumulative|ytd|year\s+to\s+date|average|avg)\b|%",
    re.I,
)
_EXPENSE_CUE_RE = re.compile(
    r"\b(cost|costs|cogs|expense|expenses|salar|wage|payroll|rent|lease|utilit|electric|water|"
    r"internet|phone|tax|taxes|insurance|fee|fees|commission|freight|shipping|logistic|fuel|"
    r"repair|maintenance|supplies|materials|purchase|purchases|marketing|advertis|travel|"
    r"depreciation|interest\s+expense|loan|amortization|subscription|software|office|benefit|"
    r"sss|philhealth|pag-?ibig|contractor|labor|labour|overhead|bank\s+charge)",
    re.I,
)
_REVENUE_CUE_RE = re.compile(
    r"\b(revenue|revenues|sales|income|turnover|receipts|fees\s+earned|service\s+income|"
    r"interest\s+income|other\s+income|subscriptions?\s+revenue|collections|billings?)\b",
    re.I,
)


# ---------------------------------------------------------------- reading

def norm_header(h: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(h or "").strip().lower())


def _cell_to_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, float):
        if v.is_integer():
            return str(int(v))
        return repr(round(v, 6))
    return str(v).strip()


def _trim_grid(grid: list[list[str]]) -> list[list[str]]:
    rows = [[c for c in r[:MAX_COLS]] for r in grid]
    while rows and not any(c for c in rows[-1]):
        rows.pop()
    width = 0
    for r in rows:
        for i in range(len(r) - 1, -1, -1):
            if r[i]:
                width = max(width, i + 1)
                break
    return [(r + [""] * width)[:width] for r in rows]


def _decode_text(raw: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError("Could not read this file's text encoding")


def _read_csv(raw: bytes) -> list[list[str]]:
    text = _decode_text(raw)
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        delim = dialect.delimiter
    except csv.Error:
        delim = ","
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    grid = []
    for i, row in enumerate(reader):
        if i > MAX_ROWS_PER_SHEET + 20:
            break
        grid.append([str(c).strip() for c in row])
    return grid


def _read_xlsx(raw: bytes) -> list[tuple[str, list[list[str]]]]:
    import openpyxl

    try:
        wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 - openpyxl raises many types
        raise ValueError("This Excel file could not be opened. Try saving it again as .xlsx") from exc
    out = []
    try:
        for ws in wb.worksheets[:MAX_SHEETS]:
            if getattr(ws, "sheet_state", "visible") != "visible":
                continue
            grid = []
            for i, row in enumerate(ws.iter_rows(values_only=True)):
                if i > MAX_ROWS_PER_SHEET + 20:
                    break
                grid.append([_cell_to_str(v) for v in row[:MAX_COLS]])
            out.append((ws.title, grid))
    finally:
        wb.close()
    return out


def read_workbook(raw: bytes, filename: str) -> list[dict]:
    """Return [{name, grid}] with blank trailing rows and columns removed."""
    if not raw:
        raise ValueError("The file is empty")
    if len(raw) > MAX_BYTES:
        raise ValueError("File is too large (max 5 MB)")
    name = (filename or "").lower()
    if name.endswith(".xls") and not name.endswith(".xlsx"):
        raise ValueError("Old .xls files aren't supported. In Excel, use File > Save As > .xlsx")
    is_xlsx = name.endswith((".xlsx", ".xlsm")) or raw[:2] == b"PK"
    if is_xlsx:
        sheets = [{"name": t, "grid": _trim_grid(g)} for t, g in _read_xlsx(raw)]
    elif name.endswith((".csv", ".tsv", ".txt")) or not name:
        base = re.sub(r"\.[a-z0-9]+$", "", filename or "Sheet 1") or "Sheet 1"
        sheets = [{"name": base, "grid": _trim_grid(_read_csv(raw))}]
    else:
        raise ValueError("Upload an Excel (.xlsx) or CSV file")
    sheets = [s for s in sheets if s["grid"]]
    if not sheets:
        raise ValueError("No data found in this file")
    return sheets


# ---------------------------------------------------------------- parsing values

def parse_amount(raw: Any) -> Optional[float]:
    s = str(raw or "").strip()
    if not s or s in ("-", "--"):
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.replace(",", "").replace(" ", "").replace(" ", "")
    s = s.strip("()")
    s = re.sub(r"^(php|usd|eur|gbp|inr|sgd|aud|cad|jpy|₱|\$|€|£|₹|p)", "", s, flags=re.I)
    s = re.sub(r"(php|usd|eur|gbp|inr)$", "", s, flags=re.I)
    if s.endswith("-"):  # trailing minus from some accounting exports
        s = "-" + s[:-1]
    try:
        v = float(s)
    except ValueError:
        return None
    if v != v or abs(v) > 1e12:  # NaN or absurd
        return None
    return round(-abs(v) if neg else v, 2)


def parse_date(raw: Any, *, assumed_year: Optional[int] = None) -> Optional[date]:
    """Parse a date. Ambiguous day/month numbers (03/04/2026) return None."""
    s = str(raw or "").strip()
    if not s:
        return None
    s = s.split("T", 1)[0].strip()
    m = re.fullmatch(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?:\s+\d{1,2}:\d{2}(:\d{2})?)?", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})", s)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000
        try:
            if a > 12 and 1 <= b <= 12:
                return date(y, b, a)
            if b > 12 and 1 <= a <= 12:
                return date(y, a, b)
        except ValueError:
            return None
        return None
    for fmt in ("%d %b %Y", "%d %B %Y", "%b %d %Y", "%B %d %Y", "%b %d, %Y", "%B %d, %Y",
                "%d-%b-%Y", "%d-%b-%y", "%d %b %y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    # Excel serial number (days since 1899-12-30), only in a plausible range.
    if re.fullmatch(r"\d{5}(\.\d+)?", s):
        n = float(s)
        if 30000 <= n <= 60000:
            from datetime import timedelta
            return date(1899, 12, 30) + timedelta(days=int(n))
    month = parse_month(s, assumed_year=assumed_year)
    if month:
        return date(int(month[:4]), int(month[5:7]), 1)
    return None


def parse_month(raw: Any, *, assumed_year: Optional[int] = None) -> Optional[str]:
    """YYYY-MM from a month header or date. Bare month names use assumed_year."""
    s = str(raw or "").strip()
    if not s:
        return None
    m = re.fullmatch(r"(\d{4})[-/.](\d{1,2})", s)
    if m and 1 <= int(m.group(2)) <= 12:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}"
    m = re.fullmatch(r"(\d{1,2})[-/.](\d{4})", s)
    if m and 1 <= int(m.group(1)) <= 12:
        return f"{int(m.group(2)):04d}-{int(m.group(1)):02d}"
    m = re.fullmatch(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})(?:\s.*)?", s)
    if m and 1 <= int(m.group(2)) <= 12:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}"
    cleaned = re.sub(r"[,.'’]", " ", s.lower())
    parts = cleaned.split()
    if 1 <= len(parts) <= 2:
        mon = _MONTHS.get(parts[0])
        yr: Optional[int] = None
        if mon and len(parts) == 2 and re.fullmatch(r"\d{2}|\d{4}", parts[1]):
            yr = int(parts[1]) + (2000 if len(parts[1]) == 2 else 0)
        elif len(parts) == 2 and _MONTHS.get(parts[1]) and re.fullmatch(r"\d{4}", parts[0]):
            mon, yr = _MONTHS[parts[1]], int(parts[0])
        elif mon and len(parts) == 1:
            yr = assumed_year
        if mon and yr:
            return f"{yr:04d}-{mon:02d}"
    return None


def _clip(v: Any, n: int = MAX_TEXT) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()[:n]


# ---------------------------------------------------------------- analyzing

def find_header_row(grid: list[list[str]]) -> int:
    """Index of the header row: skips title rows above a table."""
    window = grid[:15]
    counts = [sum(1 for c in r if c) for r in window]
    if not counts:
        return 0
    peak = max(counts)
    need = max(2, (peak + 1) // 2)
    for i, n in enumerate(counts):
        if n >= need:
            # A header row is mostly text; skip a row that is mostly numbers.
            texty = sum(1 for c in window[i] if c and parse_amount(c) is None)
            if texty >= max(1, n // 2) or parse_month(window[i][0] if window[i] else ""):
                return i
    return 0


def _match_field(header_norm: str, synonyms: list[str]) -> int:
    """Match strength: 3 exact, 2 starts/ends with, 1 contains, 0 none."""
    if not header_norm:
        return 0
    best = 0
    for syn in synonyms:
        if header_norm == syn:
            return 3
        if len(syn) >= 3 and (header_norm.startswith(syn) or header_norm.endswith(syn)):
            best = max(best, 2)
        elif len(syn) >= 4 and syn in header_norm:
            best = max(best, 1)
    return best


def map_columns(kind: str, headers: list[str]) -> dict[str, int]:
    """Greedy best match of each field to a distinct column index."""
    fields = FIELDS.get(kind, {})
    normed = [norm_header(h) for h in headers]
    candidates = []
    for field, syns in fields.items():
        for idx, hn in enumerate(normed):
            score = _match_field(hn, syns)
            if score:
                candidates.append((score, -list(fields).index(field), field, idx))
    candidates.sort(reverse=True)
    used_cols: set[int] = set()
    out: dict[str, int] = {}
    for score, _order, field, idx in candidates:
        if field in out or idx in used_cols:
            continue
        out[field] = idx
        used_cols.add(idx)
    return out


def month_columns(headers: list[str], *, assumed_year: Optional[int]) -> dict[int, str]:
    out = {}
    for idx, h in enumerate(headers):
        m = parse_month(h, assumed_year=assumed_year)
        if m:
            out[idx] = m
    return out


def _has_bare_month_headers(headers: list[str]) -> bool:
    for h in headers:
        parts = re.sub(r"[,.'’]", " ", str(h).lower()).split()
        if len(parts) == 1 and parts[0] in _MONTHS:
            return True
    return False


def _kind_score(kind: str, headers: list[str], mapping: dict[str, int]) -> float:
    if kind == KIND_FINANCIAL:
        has_money = "amount" in mapping or "money_in" in mapping or "money_out" in mapping
        if "date" not in mapping or not has_money:
            return 0.0
    else:
        for req in REQUIRED.get(kind, ()):
            if req not in mapping:
                return 0.0
    normed = [norm_header(h) for h in headers]
    score = float(len(mapping))
    for sig in KIND_SIGNALS.get(kind, []):
        if any(hn == sig or (len(sig) >= 4 and sig in hn) for hn in normed):
            score += 1.5
    return score


def analyze_sheet(sheet: dict, *, current_year: int) -> dict:
    """Best-guess plan for one sheet, without AI."""
    grid = sheet["grid"]
    hr = find_header_row(grid)
    headers = grid[hr] if grid else []
    data_rows = [r for r in grid[hr + 1:] if any(c for c in r)]
    plan: dict[str, Any] = {
        "kind": KIND_SKIP,
        "header_row": hr,
        "headers": headers,
        "columns": {},
        "label_column": None,
        "month_columns": {},
        "assumed_year": None,
        "line_types": {},
        "row_count": len(data_rows),
        "confidence": "low",
        "source": "rules",
    }
    if not headers or not data_rows:
        return plan

    # Wide P&L: two or more month headers across the top.
    bare = _has_bare_month_headers(headers)
    mcols = month_columns(headers, assumed_year=current_year)
    if len(mcols) >= 2:
        label_col = next((i for i in range(len(headers)) if i not in mcols), None)
        if label_col is not None:
            plan.update({
                "kind": KIND_FINANCIAL_WIDE,
                "label_column": label_col,
                "month_columns": {str(k): v for k, v in mcols.items()},
                "assumed_year": current_year if bare else None,
                "confidence": "high" if len(mcols) >= 3 else "medium",
            })
            # Lines in sheet order; rows without any number are section headings.
            labels: dict[str, str] = {}
            for r in data_rows:
                if label_col >= len(r) or not r[label_col]:
                    continue
                if all(parse_amount(r[c]) is None for c in mcols if c < len(r)):
                    continue
                lbl = _clip(r[label_col])
                labels.setdefault(lbl, classify_line(lbl))
            plan["line_types"] = labels
            return plan

    best_kind, best_score, best_map = KIND_SKIP, 0.0, {}
    for kind in (KIND_FINANCIAL, KIND_DEALS, KIND_PRODUCTION, KIND_PROCUREMENT, KIND_TASKS):
        mapping = map_columns(kind, headers)
        score = _kind_score(kind, headers, mapping)
        if score > best_score:
            best_kind, best_score, best_map = kind, score, mapping
    if best_kind != KIND_SKIP:
        plan["kind"] = best_kind
        plan["columns"] = {f: i for f, i in best_map.items()}
        plan["confidence"] = "high" if best_score >= 5 else "medium" if best_score >= 3 else "low"
    return plan


def classify_line(label: str) -> str:
    """revenue | expense | skip for a P&L line label (rules fallback)."""
    s = (label or "").strip()
    if not s:
        return "skip"
    if _SUMMARY_LINE_RE.search(s):
        return "skip"
    if _EXPENSE_CUE_RE.search(s):
        return "expense"
    if _REVENUE_CUE_RE.search(s):
        return "revenue"
    return "expense"


# ---------------------------------------------------------------- AI plan

AI_SYSTEM = """You map spreadsheet columns for Trenston, a company operating system.
You see a sheet's name, its header row and a few sample rows. Decide what the sheet holds and which column holds each field.
Never invent or change values. Only map columns and classify P&L line labels.

Kinds and their fields:
- financial: one row per money entry. Fields: date, amount, money_in, money_out, type, category, name. Needs date plus amount (or money_in/money_out).
- financial_wide: a P&L, budget or cash summary with line items down the side and months across the top. Give label_column and line_types.
- deals: sales pipeline or client list with deal values. Fields: name, company, value, stage, owner_name, close_date, next_step. Needs name.
- tasks: to-do or project list. Fields: title, priority, due, status, tag. Needs title.
- production: job orders, work orders or production schedule. Fields: reference, product, quantity_planned, customer, due_date, priority, notes. Needs reference.
- procurement: purchase requests, purchase orders or supplier orders. Fields: item, quantity, vendor_name, cost, expected_delivery_date, priority, notes. Needs item.
- skip: anything else (lookup tables, notes, charts, employee personal data).

Reply with JSON only:
{"kind": "...", "columns": {"field": "exact header text"}, "label_column": "exact header text or null",
 "line_types": {"exact line label": "revenue" | "expense" | "skip"}, "confidence": "high" | "medium" | "low"}
For line_types, mark totals, subtotals, profit, margin and balance lines as "skip" so nothing is counted twice."""


def ai_prompt_for_sheet(sheet: dict, plan: dict, *, max_labels: int = 150) -> str:
    """Compact prompt: sheet name, headers, a few sample rows, and P&L labels."""
    import json

    grid = sheet["grid"]
    hr = plan["header_row"]
    headers = grid[hr] if grid else []
    sample = [[_clip(c, 40) for c in r] for r in grid[hr + 1: hr + 1 + SAMPLE_ROWS]]
    body: dict[str, Any] = {
        "sheet_name": sheet["name"][:80],
        "headers": [_clip(h, 60) for h in headers],
        "sample_rows": sample,
        "rules_guess": plan["kind"],
    }
    if plan.get("kind") == KIND_FINANCIAL_WIDE and plan.get("line_types"):
        body["line_labels"] = list(plan["line_types"].keys())[:max_labels]
    return json.dumps(body, ensure_ascii=False)


def parse_ai_json(text: str) -> Optional[dict]:
    import json

    s = (text or "").strip()
    s = re.sub(r"^```(?:json)?\s*|\s*```$", "", s)
    start, end = s.find("{"), s.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(s[start: end + 1])
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def merge_ai_plan(plan: dict, ai: Optional[dict], *, current_year: int) -> dict:
    """Apply a validated AI mapping on top of the rules plan. Bad AI output is ignored."""
    if not ai:
        return plan
    kind = str(ai.get("kind") or "").strip().lower()
    if kind not in ALL_KINDS:
        return plan
    headers = plan.get("headers") or []
    by_norm = {}
    for i, h in enumerate(headers):
        by_norm.setdefault(_clip(h, 60).lower(), i)

    def col_of(name: Any) -> Optional[int]:
        if name is None:
            return None
        return by_norm.get(_clip(name, 60).lower())

    out = dict(plan)
    if kind == KIND_SKIP:
        out.update({"kind": KIND_SKIP, "source": "ai", "confidence": str(ai.get("confidence") or "medium")})
        return out
    if kind == KIND_FINANCIAL_WIDE:
        label_col = col_of(ai.get("label_column"))
        if label_col is None:
            label_col = plan.get("label_column")
        mcols = month_columns(headers, assumed_year=current_year)
        if label_col is not None:
            mcols.pop(label_col, None)
        if label_col is None or len(mcols) < 2:
            return plan
        types = dict(plan.get("line_types") or {})
        ai_types = ai.get("line_types") if isinstance(ai.get("line_types"), dict) else {}
        lowered = {k.lower(): k for k in types}
        for lbl, t in ai_types.items():
            key = lowered.get(_clip(lbl).lower())
            if key and t in ("revenue", "expense", "skip"):
                types[key] = t
        out.update({
            "kind": KIND_FINANCIAL_WIDE, "label_column": label_col,
            "month_columns": {str(k): v for k, v in mcols.items()},
            "line_types": types, "columns": {}, "source": "ai",
            "confidence": str(ai.get("confidence") or "medium"),
        })
        return out
    cols_in = ai.get("columns") if isinstance(ai.get("columns"), dict) else {}
    allowed = set(FIELDS.get(kind, {}).keys())
    cols: dict[str, int] = {}
    used: set[int] = set()
    for field, header in cols_in.items():
        if field not in allowed:
            continue
        idx = col_of(header)
        if idx is None or idx in used:
            continue
        cols[field] = idx
        used.add(idx)
    if _kind_score(kind, headers, cols) <= 0:
        return plan  # AI mapping misses a required field: keep the rules plan
    out.update({
        "kind": kind, "columns": cols, "source": "ai",
        "label_column": None, "month_columns": {}, "line_types": {},
        "confidence": str(ai.get("confidence") or "medium"),
    })
    return out


# ---------------------------------------------------------------- building records

_TYPE_WORDS = {
    "revenue": "revenue", "income": "revenue", "sales": "revenue", "sale": "revenue", "in": "revenue",
    "credit": "revenue", "deposit": "revenue", "receipt": "revenue", "moneyin": "revenue",
    "expense": "expense", "expenses": "expense", "cost": "expense", "costs": "expense", "out": "expense",
    "debit": "expense", "payment": "expense", "withdrawal": "expense", "moneyout": "expense", "purchase": "expense",
}


def deal_stage(raw: Any) -> str:
    s = norm_header(raw)
    if not s:
        return "lead"
    if "lost" in s or "dead" in s or "cancel" in s or "declin" in s or "rejected" in s:
        return "lost"
    if "won" in s or "signed" in s or "closedwon" in s or s in ("closed", "paid", "done", "converted", "client", "active"):
        return "won"
    if "negot" in s or "contract" in s:
        return "negotiation"
    if "propos" in s or "quot" in s or "offer" in s:
        return "proposal"
    if "qualif" in s or "meeting" in s or "demo" in s or "discovery" in s or "contacted" in s:
        return "qualified"
    return "lead"


def task_column(raw: Any) -> str:
    s = norm_header(raw)
    if not s:
        return "backlog"
    if s in ("done", "complete", "completed", "finished", "closed", "yes", "true", "100", "x") or "done" in s or "complet" in s:
        return "done"
    if "review" in s or "check" in s or "approval" in s:
        return "review"
    if "progress" in s or "doing" in s or "ongoing" in s or "started" in s or "wip" in s or "active" in s:
        return "in_progress"
    return "backlog"


def task_priority(raw: Any) -> str:
    s = norm_header(raw)
    if s in ("high", "urgent", "critical", "p0", "p1", "1", "asap", "top"):
        return "High"
    if s in ("low", "p3", "p4", "3", "4", "minor", "later"):
        return "Low"
    return "Medium"


def ops_priority(raw: Any) -> str:
    s = norm_header(raw)
    if s in ("high", "urgent", "critical", "rush", "p0", "p1", "1", "asap"):
        return "high"
    if s in ("low", "p3", "p4", "3", "4", "minor"):
        return "low"
    return "normal"


def _get(row: list[str], cols: dict, field: str) -> str:
    idx = cols.get(field)
    if idx is None or idx >= len(row):
        return ""
    return row[idx]


def build_records(sheet: dict, plan: dict, *, current_month: str, current_year: int) -> dict:
    """Turn a sheet into records for its kind. Returns {records, skipped, notes}."""
    kind = plan.get("kind")
    grid = sheet["grid"]
    hr = int(plan.get("header_row") or 0)
    rows = grid[hr + 1:]
    records: list[dict] = []
    skipped: list[dict] = []
    notes: list[str] = []
    cols = {k: int(v) for k, v in (plan.get("columns") or {}).items()}

    def skip(rownum: int, reason: str) -> None:
        if len(skipped) < 200:
            skipped.append({"row": rownum, "reason": reason})

    if kind == KIND_FINANCIAL_WIDE:
        label_col = plan.get("label_column")
        mcols = {int(k): v for k, v in (plan.get("month_columns") or {}).items()}
        types = plan.get("line_types") or {}
        future_cells = 0
        section = ""
        for i, row in enumerate(rows):
            rownum = hr + i + 2
            if label_col is None or label_col >= len(row):
                continue
            label = _clip(row[label_col])
            values = {m: parse_amount(row[c]) for c, m in mcols.items() if c < len(row)}
            if not label:
                continue
            if all(v is None for v in values.values()):
                section = label  # a heading like "Operating expenses"
                continue
            t = types.get(label) or classify_line(label)
            if t == "skip":
                skip(rownum, f'"{label}" looks like a total, so it was left out')
                continue
            for month, amount in sorted(values.items()):
                if amount is None or amount == 0:
                    continue
                if month > current_month:
                    future_cells += 1
                    continue
                entry_type = t
                if amount < 0:
                    # A negative revenue line is a refund or discount: book it as an expense.
                    amount = abs(amount)
                    entry_type = "expense" if t == "revenue" else "revenue"
                records.append({
                    "type": entry_type, "amount": round(amount, 2), "month": month,
                    "category": _clip(section or label, 80) or "Other", "name": label,
                    "note": "", "source_row": rownum,
                })
        if future_cells:
            notes.append(
                f"{future_cells} value{'s' if future_cells != 1 else ''} in future months were left out. "
                "Trenston stores what actually happened; use Financial Modeling for forecasts."
            )
        if plan.get("assumed_year"):
            notes.append(f"Months without a year were read as {plan['assumed_year']}.")
        return {"records": records, "skipped": skipped, "notes": notes}

    for i, row in enumerate(rows):
        rownum = hr + i + 2
        if not any(c for c in row):
            continue
        if kind == KIND_FINANCIAL:
            when = parse_date(_get(row, cols, "date"), assumed_year=current_year)
            if not when:
                skip(rownum, "No readable date")
                continue
            month = when.strftime("%Y-%m")
            if month > current_month:
                skip(rownum, "Date is in the future")
                continue
            amount: Optional[float] = None
            entry_type: Optional[str] = None
            if "money_in" in cols or "money_out" in cols:
                vin = parse_amount(_get(row, cols, "money_in"))
                vout = parse_amount(_get(row, cols, "money_out"))
                if vin:
                    amount, entry_type = abs(vin), "revenue"
                elif vout:
                    amount, entry_type = abs(vout), "expense"
            if amount is None and "amount" in cols:
                amount = parse_amount(_get(row, cols, "amount"))
                if amount is not None:
                    raw_type = norm_header(_get(row, cols, "type"))
                    entry_type = _TYPE_WORDS.get(raw_type)
                    if entry_type is None:
                        entry_type = "expense" if amount < 0 else "revenue"
                    amount = abs(amount)
            if not amount:
                skip(rownum, "No amount")
                continue
            name = _clip(_get(row, cols, "name"))
            category = _clip(_get(row, cols, "category"), 80) or ("Sales" if entry_type == "revenue" else "Other")
            if _SUMMARY_LINE_RE.fullmatch(name or "") or norm_header(name) in ("total", "subtotal", "balance"):
                skip(rownum, "Looks like a total row")
                continue
            records.append({
                "type": entry_type, "amount": round(amount, 2), "month": month,
                "category": category, "name": name, "note": "", "source_row": rownum,
            })
        elif kind == KIND_DEALS:
            name = _clip(_get(row, cols, "name"))
            company = _clip(_get(row, cols, "company"))
            if not name and company:
                name = company
            if not name:
                skip(rownum, "No deal or client name")
                continue
            if norm_header(name) in ("total", "subtotal", "grandtotal"):
                skip(rownum, "Looks like a total row")
                continue
            value = parse_amount(_get(row, cols, "value"))
            close = parse_date(_get(row, cols, "close_date"), assumed_year=current_year)
            records.append({
                "name": name, "company": company if company != name else "",
                "value": round(abs(value), 2) if value else 0.0,
                "stage": deal_stage(_get(row, cols, "stage")),
                "owner_name": _clip(_get(row, cols, "owner_name"), 120),
                "close_date": close.isoformat() if close else "",
                "next_step": _clip(_get(row, cols, "next_step"), 280),
                "source_row": rownum,
            })
        elif kind == KIND_TASKS:
            title = _clip(_get(row, cols, "title"))
            if not title:
                skip(rownum, "No task title")
                continue
            due = parse_date(_get(row, cols, "due"), assumed_year=current_year)
            records.append({
                "title": title,
                "priority": task_priority(_get(row, cols, "priority")),
                "due": due.isoformat() if due else "",
                "column": task_column(_get(row, cols, "status")),
                "tag": _clip(_get(row, cols, "tag"), 40) or "General",
                "source_row": rownum,
            })
        elif kind == KIND_PRODUCTION:
            ref = _clip(_get(row, cols, "reference"))
            if not ref:
                skip(rownum, "No job or order number")
                continue
            if norm_header(ref) in ("total", "subtotal"):
                skip(rownum, "Looks like a total row")
                continue
            qty = parse_amount(_get(row, cols, "quantity_planned"))
            due = parse_date(_get(row, cols, "due_date"), assumed_year=current_year)
            records.append({
                "reference": ref,
                "product": _clip(_get(row, cols, "product")),
                "quantity_planned": abs(qty) if qty else None,
                "customer": _clip(_get(row, cols, "customer")),
                "due_date": due.isoformat() if due else "",
                "priority": ops_priority(_get(row, cols, "priority")),
                "notes": _clip(_get(row, cols, "notes"), 500),
                "source_row": rownum,
            })
        elif kind == KIND_PROCUREMENT:
            item = _clip(_get(row, cols, "item"))
            if not item:
                skip(rownum, "No item name")
                continue
            if norm_header(item) in ("total", "subtotal", "grandtotal"):
                skip(rownum, "Looks like a total row")
                continue
            qty = parse_amount(_get(row, cols, "quantity"))
            cost = parse_amount(_get(row, cols, "cost"))
            eta = parse_date(_get(row, cols, "expected_delivery_date"), assumed_year=current_year)
            records.append({
                "item": item,
                "quantity": abs(qty) if qty else 1.0,
                "vendor_name": _clip(_get(row, cols, "vendor_name")),
                "cost": round(abs(cost), 2) if cost is not None else None,
                "expected_delivery_date": eta.isoformat() if eta else "",
                "priority": ops_priority(_get(row, cols, "priority")),
                "notes": _clip(_get(row, cols, "notes"), 500),
                "source_row": rownum,
            })
    if len(records) > MAX_ROWS_PER_SHEET:
        notes.append(f"Only the first {MAX_ROWS_PER_SHEET} rows were read.")
        records = records[:MAX_ROWS_PER_SHEET]
    return {"records": records, "skipped": skipped, "notes": notes}


# ---------------------------------------------------------------- confirm-time validation

def _iso_date_or_blank(v: Any) -> str:
    s = str(v or "").strip()[:10]
    if not s:
        return ""
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return s
    except ValueError:
        return ""


def clean_record(record_kind: str, raw: Any, *, current_month: str) -> Optional[dict]:
    """Re-validate one record sent back by the browser. None = drop it."""
    if not isinstance(raw, dict):
        return None
    if record_kind == "financial":
        t = str(raw.get("type") or "").strip().lower()
        if t not in ("revenue", "expense"):
            return None
        try:
            amount = round(float(raw.get("amount")), 2)
        except (TypeError, ValueError):
            return None
        if not (0 < amount <= 1e12):
            return None
        month = str(raw.get("month") or "").strip()
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month) or month > current_month:
            return None
        return {
            "type": t, "amount": amount, "month": month,
            "category": _clip(raw.get("category"), 80) or "Other",
            "name": _clip(raw.get("name")), "note": _clip(raw.get("note"), 500),
        }
    if record_kind == "deal":
        name = _clip(raw.get("name"))
        if not name:
            return None
        try:
            value = round(float(raw.get("value") or 0), 2)
        except (TypeError, ValueError):
            value = 0.0
        stage = str(raw.get("stage") or "lead")
        if stage not in ("lead", "qualified", "proposal", "negotiation", "won", "lost"):
            stage = "lead"
        return {
            "name": name, "company": _clip(raw.get("company")),
            "value": max(0.0, min(value, 1e12)), "stage": stage,
            "owner_name": _clip(raw.get("owner_name"), 120),
            "close_date": _iso_date_or_blank(raw.get("close_date")),
            "next_step": _clip(raw.get("next_step"), 280),
        }
    if record_kind == "task":
        title = _clip(raw.get("title"))
        if not title:
            return None
        col = str(raw.get("column") or "backlog")
        if col not in ("backlog", "in_progress", "review", "done"):
            col = "backlog"
        pr = str(raw.get("priority") or "Medium")
        if pr not in ("High", "Medium", "Low"):
            pr = "Medium"
        return {
            "title": title, "priority": pr, "due": _iso_date_or_blank(raw.get("due")),
            "column": col, "tag": _clip(raw.get("tag"), 40) or "General",
        }
    if record_kind == "work_order":
        ref = _clip(raw.get("reference"))
        if not ref:
            return None
        qty = raw.get("quantity_planned")
        try:
            qty = None if qty in (None, "") else max(0.0, min(float(qty), 1e12))
        except (TypeError, ValueError):
            qty = None
        pr = str(raw.get("priority") or "normal")
        return {
            "reference": ref, "product": _clip(raw.get("product")), "quantity_planned": qty,
            "customer": _clip(raw.get("customer")), "due_date": _iso_date_or_blank(raw.get("due_date")),
            "priority": pr if pr in ("low", "normal", "high") else "normal",
            "notes": _clip(raw.get("notes"), 2000),
        }
    if record_kind == "purchase_request":
        item = _clip(raw.get("item"))
        if not item:
            return None
        try:
            qty = float(raw.get("quantity") or 1)
        except (TypeError, ValueError):
            qty = 1.0
        if qty <= 0:
            qty = 1.0
        cost = raw.get("cost")
        try:
            cost = None if cost in (None, "") else round(max(0.0, min(float(cost), 1e12)), 2)
        except (TypeError, ValueError):
            cost = None
        pr = str(raw.get("priority") or "normal")
        return {
            "item": item, "quantity": min(qty, 1e12), "vendor_name": _clip(raw.get("vendor_name")),
            "cost": cost, "expected_delivery_date": _iso_date_or_blank(raw.get("expected_delivery_date")),
            "priority": pr if pr in ("low", "normal", "high") else "normal",
            "notes": _clip(raw.get("notes"), 2000),
        }
    return None


def column_labels(plan: dict) -> dict[str, str]:
    """field -> header text, for showing the mapping in the preview."""
    headers = plan.get("headers") or []
    out = {}
    for field, idx in (plan.get("columns") or {}).items():
        if 0 <= int(idx) < len(headers):
            out[field] = _clip(headers[int(idx)], 60)
    if plan.get("kind") == KIND_FINANCIAL_WIDE and plan.get("label_column") is not None:
        lc = int(plan["label_column"])
        if lc < len(headers):
            out["line"] = _clip(headers[lc], 60) or "First column"
    return out


def summarize(kind: str, records: list[dict]) -> dict:
    """Small totals for the preview card."""
    if kind in (KIND_FINANCIAL, KIND_FINANCIAL_WIDE):
        rev = round(sum(r["amount"] for r in records if r["type"] == "revenue"), 2)
        exp = round(sum(r["amount"] for r in records if r["type"] == "expense"), 2)
        months = sorted({r["month"] for r in records})
        return {"revenue": rev, "expenses": exp,
                "first_month": months[0] if months else None,
                "last_month": months[-1] if months else None,
                "months": len(months)}
    if kind == KIND_DEALS:
        open_v = round(sum(r["value"] for r in records if r["stage"] not in ("won", "lost")), 2)
        return {"open_value": open_v, "won": sum(1 for r in records if r["stage"] == "won")}
    if kind == KIND_TASKS:
        return {"open": sum(1 for r in records if r["column"] != "done")}
    return {}
