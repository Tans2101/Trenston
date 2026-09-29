"""Regenerate shared/modeling-parity.json from the Python reference model.

Run after an intentional change to backend/modeling.py, then update
frontend/src/lib/modeling.js until its parity test passes again.
    python3 backend/scripts/gen_modeling_parity.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
import modeling  # noqa: E402

BASE = {"cash": 10000, "revenue": 1000, "expenses": 3000, "start_month": "2026-09"}

CASES = [
    ("flat burn, runs out in exactly 5 months",
     {"horizon": 12, "min_cash_reserve": 5000}, BASE),
    ("profitable company, cash growing",
     {"horizon": 12}, {"cash": 5000, "revenue": 5000, "expenses": 3000, "start_month": "2026-09"}),
    ("cash not entered",
     {"horizon": 12, "revenue_growth_pct": 5}, {"cash": None, "revenue": 1000, "expenses": 3000, "start_month": "2026-09"}),
    ("no ledger at all",
     {"horizon": 12}, {"cash": 10000, "revenue": None, "expenses": None, "start_month": "2026-09"}),
    ("revenue unknown, expenses known",
     {"horizon": 12}, {"cash": 20000, "revenue": None, "expenses": 2500, "start_month": "2026-12"}),
    ("growth, hires and a funding round over 36 months",
     {"horizon": 36, "revenue_growth_pct": 8, "expense_growth_pct": 2,
      "hires": [{"label": "Engineer", "monthly_cost": 4000, "start_month": 3},
                {"label": "Sales", "monthly_cost": 2500, "start_month": 7}],
      "events": [{"label": "Seed round", "amount": 150000, "month": 6},
                 {"label": "Laptops", "amount": -6000, "month": 3}],
      "min_cash_reserve": 20000},
     {"cash": 60000, "revenue": 4000, "expenses": 9000, "start_month": "2026-09"}),
    ("out-of-range and junk inputs are clamped or defaulted",
     {"horizon": 18, "revenue_growth_pct": -80, "expense_growth_pct": "NaN",
      "hires": [{"label": "  Ops  ", "monthly_cost": -50, "start_month": 99}, "junk",
                {"label": True, "monthly_cost": "1500", "start_month": "0x10"}],
      "events": [{"label": "x" * 80, "amount": "1e3", "month": 2.9}],
      "min_cash_reserve": -10},
     {"cash": "12000", "revenue": "", "expenses": "2000", "start_month": "2026-01"}),
    ("already overdrawn",
     {"horizon": 12, "min_cash_reserve": 1000}, {"cash": -500, "revenue": 1000, "expenses": 1500, "start_month": "2026-09"}),
    ("huge values stay finite",
     {"horizon": 24, "revenue_growth_pct": 100, "expense_growth_pct": 100},
     {"cash": 1e11, "revenue": 1e9, "expenses": 2e9, "start_month": "2026-09"}),
    ("slow burn lasts beyond the horizon",
     {"horizon": 12}, {"cash": 100000, "revenue": 9000, "expenses": 10000, "start_month": "2026-09"}),
    ("break-even reached through revenue growth",
     {"horizon": 24, "revenue_growth_pct": 10}, {"cash": 50000, "revenue": 2000, "expenses": 4000, "start_month": "2026-11"}),
    ("zero cash, zero burn edge",
     {"horizon": 12}, {"cash": 0, "revenue": 0, "expenses": 0, "start_month": "2026-09"}),
    ("inputs not an object",
     None, BASE),
]

out = []
for name, inputs, baseline in CASES:
    out.append({
        "name": name,
        "inputs": inputs,
        "baseline": baseline,
        "sanitized": modeling.sanitize_inputs(inputs),
        "expected": modeling.project_cash(inputs, baseline),
    })
path = ROOT / "shared" / "modeling-parity.json"
path.write_text(json.dumps({"cases": out}, indent=1) + "\n")
print(f"wrote {len(out)} cases to {path}")
