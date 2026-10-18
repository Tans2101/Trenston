/**
 * Quick import (drop a file, get a company): pure helpers for the review screen.
 * The server reads the file and returns records; these helpers apply the
 * owner's choices (which sheets, how each P&L line counts) before confirm.
 */

export const ACCEPTED_FILES = ".xlsx,.xlsm,.csv";
export const MAX_FILE_BYTES = 5 * 1024 * 1024;

const NOUNS = {
  financial: ["money entry", "money entries"],
  financial_wide: ["money entry", "money entries"],
  deals: ["deal", "deals"],
  tasks: ["task", "tasks"],
  production: ["production order", "production orders"],
  procurement: ["purchase request", "purchase requests"],
};

export function recordsLabel(kind, n) {
  const pair = NOUNS[kind] || ["row", "rows"];
  return `${n.toLocaleString()} ${n === 1 ? pair[0] : pair[1]}`;
}

/** Friendly names for mapped fields, shown as "Client → Deal name". */
export const FIELD_LABELS = {
  date: "Date",
  amount: "Amount",
  money_in: "Money in",
  money_out: "Money out",
  type: "Revenue or expense",
  category: "Category",
  name: "Name",
  company: "Company",
  value: "Deal value",
  stage: "Stage",
  owner_name: "Owner",
  close_date: "Close date",
  next_step: "Next step",
  title: "Task",
  priority: "Priority",
  due: "Due date",
  status: "Status",
  tag: "Tag",
  reference: "Order number",
  product: "Product",
  quantity_planned: "Quantity",
  customer: "Customer",
  due_date: "Due date",
  notes: "Notes",
  item: "Item",
  quantity: "Quantity",
  vendor_name: "Supplier",
  cost: "Cost",
  expected_delivery_date: "Delivery date",
  line: "Line items",
};

export function fieldLabel(kind, field) {
  if (kind === "deals" && field === "name") return "Deal name";
  if (field === "name" && (kind === "financial" || kind === "financial_wide")) return "Description";
  return FIELD_LABELS[field] || field;
}

/** Where each kind lands in the app, for the done screen. */
export const KIND_DESTINATION = {
  financial: { label: "Financials", to: "/app/financials" },
  financial_wide: { label: "Financials", to: "/app/financials" },
  deals: { label: "Sales", to: "/app/sales" },
  tasks: { label: "Tasks", to: "/app/tasks" },
  production: { label: "Production", to: "/app/departments/production" },
  procurement: { label: "Procurement", to: "/app/departments/procurement" },
};

export const COUNT_TO_KIND = {
  financial: "financial",
  deal: "deals",
  task: "tasks",
  work_order: "production",
  purchase_request: "procurement",
};

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-11-15" -> "15 Nov 2026"; anything else is returned as is. */
export function dayName(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(iso || ""));
  if (!m) return String(iso || "");
  return `${Number(m[3])} ${MONTHS[Number(m[2]) - 1]} ${m[1]}`;
}

export function monthName(ym) {
  const m = /^(\d{4})-(\d{2})$/.exec(String(ym || ""));
  if (!m) return String(ym || "");
  return `${MONTHS[Number(m[2]) - 1]} ${m[1]}`;
}

const STAGE_LABEL = {
  lead: "Lead", qualified: "Qualified", proposal: "Proposal",
  negotiation: "Negotiation", won: "Won", lost: "Lost",
};
const COLUMN_LABEL = { backlog: "To-Do", in_progress: "In progress", review: "Review", done: "Done" };

/** Columns for the small sample table on each sheet card. */
export function sampleColumns(kind, money) {
  const amt = (v) => (v == null || v === "" ? "" : money(v));
  switch (kind) {
    case "financial":
    case "financial_wide":
      return [
        { key: "month", label: "Month", get: (r) => monthName(r.month) },
        { key: "name", label: "Line", get: (r) => r.name || r.category },
        { key: "type", label: "Type", get: (r) => (r.type === "revenue" ? "Revenue" : "Expense"), optional: true },
        { key: "amount", label: "Amount", get: (r) => amt(r.amount), num: true },
      ];
    case "deals":
      return [
        { key: "name", label: "Deal", get: (r) => r.name },
        { key: "stage", label: "Stage", get: (r) => STAGE_LABEL[r.stage] || r.stage },
        { key: "value", label: "Value", get: (r) => (r.value ? amt(r.value) : ""), num: true },
        { key: "close", label: "Close", get: (r) => dayName(r.close_date), optional: true },
      ];
    case "tasks":
      return [
        { key: "title", label: "Task", get: (r) => r.title },
        { key: "column", label: "Status", get: (r) => COLUMN_LABEL[r.column] || r.column },
        { key: "due", label: "Due", get: (r) => dayName(r.due) },
        { key: "priority", label: "Priority", get: (r) => r.priority, optional: true },
      ];
    case "production":
      return [
        { key: "reference", label: "Order", get: (r) => r.reference },
        { key: "product", label: "Product", get: (r) => r.product },
        { key: "qty", label: "Qty", get: (r) => (r.quantity_planned == null ? "" : Number(r.quantity_planned).toLocaleString()), num: true },
        { key: "due", label: "Due", get: (r) => dayName(r.due_date), optional: true },
      ];
    case "procurement":
      return [
        { key: "item", label: "Item", get: (r) => r.item },
        { key: "vendor", label: "Supplier", get: (r) => r.vendor_name, optional: true },
        { key: "qty", label: "Qty", get: (r) => Number(r.quantity || 0).toLocaleString(), num: true },
        { key: "cost", label: "Cost", get: (r) => amt(r.cost), num: true },
      ];
    default:
      return [];
  }
}

function flipType(t) {
  return t === "revenue" ? "expense" : "revenue";
}

/**
 * Apply the owner's P&L line choices to a sheet's records.
 * original: {label: type} from the server; chosen: {label: type} now.
 * A line switched to "skip" is dropped; a revenue/expense switch flips its rows
 * (keeping refunds, which the server already booked the other way, consistent).
 */
export function applyLineTypes(records, original, chosen) {
  if (!chosen || !Object.keys(chosen).length) return records;
  const out = [];
  for (const r of records) {
    const was = original?.[r.name];
    const now = chosen[r.name];
    if (!now || !was || now === was) {
      out.push(r);
      continue;
    }
    if (now === "skip") continue;
    if (was === "skip") {
      out.push({ ...r, type: now });
      continue;
    }
    out.push({ ...r, type: flipType(r.type) });
  }
  return out;
}

/** Records the confirm call will send for one sheet, after the owner's choices. */
export function sheetRecords(sheet, choice) {
  if (!choice?.include) return [];
  if (sheet.kind === "financial_wide") {
    const original = Object.fromEntries((sheet.line_types || []).map((l) => [l.label, l.type]));
    return applyLineTypes(sheet.records || [], original, choice.lineTypes || {});
  }
  return sheet.records || [];
}

export function buildConfirmPayload(preview, choices) {
  const sheets = [];
  for (const s of preview?.sheets || []) {
    const records = sheetRecords(s, choices[s.index]);
    if (!records.length) continue;
    sheets.push({
      name: s.name,
      kind: s.kind,
      records: records.map(({ source_row: _row, ...rest }) => rest),
    });
  }
  return { filename: preview?.filename || "", sheets };
}

export function initialChoices(preview) {
  const out = {};
  for (const s of preview?.sheets || []) {
    const importable = s.kind !== "skip" && (s.records || []).length > 0;
    out[s.index] = {
      // A low-confidence guess starts unticked so nothing surprising lands.
      include: importable && s.confidence !== "low",
      lineTypes: {},
    };
  }
  return out;
}

export function totalSelected(preview, choices) {
  return (preview?.sheets || []).reduce((n, s) => n + sheetRecords(s, choices[s.index]).length, 0);
}

/** "12 money entries, 3 deals" for the done screen. */
export function countsSentence(counts) {
  const parts = [];
  for (const [k, n] of Object.entries(counts || {})) {
    if (!n) continue;
    parts.push(recordsLabel(COUNT_TO_KIND[k] || k, n));
  }
  if (parts.length <= 1) return parts[0] || "Nothing";
  return `${parts.slice(0, -1).join(", ")} and ${parts[parts.length - 1]}`;
}
