# Trenston data model

How money data moves from where it is entered to the numbers a CEO sees, and
the rules every surface follows. Read this before touching anything that
shows cash, burn, runway, MRR or ARR.

## Layers

Trenston follows the bronze / silver / gold pattern, scaled to one Mongo
database.

| Layer | What it is | Where it lives |
|---|---|---|
| Raw (bronze) | Provider records as QuickBooks, Xero and SAP B1 hold them | The provider itself. Trenston does not copy raw payloads (less sensitive data held; a full re-pull rebuilds everything). |
| Ledger (silver) | One row per revenue or expense line, in a shared shape, with home-currency amounts | `financial_entries`. Written by manual entry, CSV import, bill upload, deals, purchase requests and the accounting sync (`_upsert_accounting_sync_entries`). |
| Monthly totals (gold) | Revenue and expenses per month, recurring rows expanded, future-dated rows held back | `compute_financials` in `server.py` (`ledger_months`, `revenue_series`, `burn_series`). Cached per workspace and invalidated on every write. |
| Metrics (semantic) | What each headline number means and how it is computed | `backend/metric_definitions.py` |

## Metric rules

All of these live in `metric_definitions.py`. Do not re-derive them in another
module, an AI prompt or the frontend.

- **Unknown is not zero.** A figure never entered is `None` and shows as
  "Add data". One-time sales never make MRR $0.
- **Completed months.** Average net burn uses the last 3 completed months.
  The current month counts only when no month is complete yet, and the UI
  then calls runway an early estimate.
- **Signed burn.** Net burn is expenses minus revenue. A profitable month
  lowers the average. Average burn at or below zero means cash is growing
  and there is no runway limit.
- **Runway** is cash in bank divided by average net burn, one decimal.
- **MRR** is recurring revenue in the latest ledger month. **ARR** is MRR x 12.
- **Home currency.** Totals use `amount_home` / `amount_net_home` when present.

The Financials headline runway, the Model page "current trajectory", the
cash reserve forecast and the AI all start from the same burn basis.
`tests/test_data_model.py` checks they agree.

Every response from `compute_financials` carries `avg_burn_value`,
`burn_window` and `runway_basis` (for example "Based on average net burn
over Jul 2026 to Sep 2026."), so any surface can say what runway is based on.

## Data quality checks

Run daily by the anomaly scan in `automations.py`:

- `duplicate_entry`: identical name, amount and month entered twice.
- `cross_source_duplicate`: a row added in Trenston (by hand, recurring, or
  from a deal or purchase request) that matches a row synced from
  accounting for the same type, month and amount (0.5% slack for rounding).
  Recent 6 months, material amounts only.
- `outlier_expense`, `revenue_drop`, `revenue_stopped`.

## Lineage and re-mapping

Synced rows keep `qb_txn_id` (stable provider id), `source`,
`source_entity` and `mapping_version`.

When you change how a provider record becomes a ledger row (category, sign,
tax, currency, month), bump `accounting_map.MAPPING_VERSION`. On its next
sync, each workspace sees that its stored `<provider>_mapping_version`
differs, re-pulls everything from the provider once, and rewrites every row
with the new logic. Upserts are idempotent, so the re-pull is safe.

## AI output history (`ai_output_log`)

Every AI briefing note and Money summary is appended to `ai_output_log`, one
chain per workspace (`backend/ai_audit.py`). Records are insert-only. Each holds
the text, `input_hash` (SHA-256 fingerprint of the exact data the AI was given),
the model, who asked, the time, `prev_hash` and its own `hash`. Editing or
deleting an old record breaks the chain; `ai_audit.verify_chain` reports the
first broken `seq`. A unique index on `(workspace_id, seq)` keeps concurrent
writers from forking the chain. Workspace deletion removes the log with the rest
of the workspace. External timestamping of the chain tip is a later step.
