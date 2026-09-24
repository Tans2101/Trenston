import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Plus, X } from "lucide-react";
import CirDeleteBtn from "@/components/CirDeleteBtn";
import CirEditBtn from "@/components/CirEditBtn";
import { useFetch, fetchErrorMessage } from "@/hooks/useFetch";
import { api, apiErrorMessage } from "@/lib/api";
import { GlassCard, SectionLabel, EmptyState, ErrorScreen } from "@/components/kit";
import { thisMonthISO } from "@/lib/dates";
import { useWorkspaceTimezone } from "@/hooks/useWorkspaceTimezone";

const money = (n) => {
  const v = Number(n) || 0;
  if (v >= 1000000) return `$${(v / 1000000).toFixed(v >= 10000000 ? 0 : 1)}M`;
  if (v >= 1000) return `$${(v / 1000).toFixed(v >= 10000 ? 0 : 1)}k`;
  return `$${v.toLocaleString()}`;
};

const emptyEntry = () => ({
  buyer_name: "",
  country: "",
  product: "",
  price: "",
  quantity: "",
  status: "expected",
  expected_close_month: "",
  notes: "",
});

/** Next 18 months as YYYY-MM options for the expected-closing picker. */
function closingMonthOptions(anchor = new Date()) {
  const opts = [];
  const y = anchor.getUTCFullYear();
  const m = anchor.getUTCMonth(); // 0-based
  for (let i = -1; i < 17; i += 1) {
    const d = new Date(Date.UTC(y, m + i, 1));
    const value = `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
    const label = d.toLocaleString(undefined, { month: "long", year: "numeric", timeZone: "UTC" });
    opts.push({ value, label });
  }
  return opts;
}

function formatCloseMonth(ym) {
  if (!ym || String(ym).length < 7) return "—";
  const [ys, ms] = String(ym).slice(0, 7).split("-");
  const d = new Date(Date.UTC(Number(ys), Number(ms) - 1, 1));
  if (Number.isNaN(d.getTime())) return ym;
  return d.toLocaleString(undefined, { month: "short", year: "numeric", timeZone: "UTC" });
}

/**
 * Sales order book + monthly target panel.
 * Mounted as a tab alongside the existing pipeline board.
 */
export default function SalesOrderBook() {
  const { data, loading, error, reload } = useFetch("/sales/order-book");
  const tz = useWorkspaceTimezone();
  const [filterCountry, setFilterCountry] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [adding, setAdding] = useState(false);
  const [editingId, setEditingId] = useState(null);
  const [form, setForm] = useState(emptyEntry);
  const [busy, setBusy] = useState(false);
  const [targetDraft, setTargetDraft] = useState("");
  const monthOptions = useMemo(() => closingMonthOptions(), []);

  const entries = useMemo(() => data?.entries || [], [data?.entries]);
  const summary = data?.summary || null;
  const tvs = data?.target_vs_actual || null;
  const canManageTarget = Boolean(data?.is_lead || data?.is_ceo);
  const myId = data?.my_user_id;

  useEffect(() => {
    if (tvs?.target_entered && tvs.target != null) setTargetDraft(String(tvs.target));
    else setTargetDraft("");
  }, [tvs?.target, tvs?.target_entered]);

  const countries = useMemo(() => {
    const set = new Set(entries.map((e) => e.country).filter(Boolean));
    return [...set].sort();
  }, [entries]);

  const visible = useMemo(() => {
    return entries.filter((e) => {
      if (filterStatus && e.status !== filterStatus) return false;
      if (filterCountry && (e.country || "").toLowerCase() !== filterCountry.toLowerCase()) return false;
      return true;
    });
  }, [entries, filterCountry, filterStatus]);

  const monthSelectOptions = useMemo(() => {
    const values = new Set(monthOptions.map((o) => o.value));
    if (form.expected_close_month && !values.has(form.expected_close_month)) {
      return [
        { value: form.expected_close_month, label: formatCloseMonth(form.expected_close_month) },
        ...monthOptions,
      ];
    }
    return monthOptions;
  }, [monthOptions, form.expected_close_month]);

  if (loading) {
    return <p className="text-sm text-helm-muted">Loading order book…</p>;
  }
  if (error) {
    const status = error?.response?.status;
    if (status === 403 || status === 404) {
      return (
        <ErrorScreen
          label={status === 403 ? "Access denied" : "Sales not enabled"}
          message={status === 403
            ? "You are not a member of Sales."
            : "Enable Sales under Settings → Departments first."}
          onRetry={reload}
        />
      );
    }
    return (
      <ErrorScreen
        label="Could not load order book"
        message={fetchErrorMessage(error, "Order book unavailable.")}
        onRetry={reload}
      />
    );
  }

  const canMutate = (e) => Boolean(data?.is_lead || data?.is_ceo || e.created_by_user_id === myId);

  const saveTarget = async () => {
    const raw = targetDraft.trim();
    if (raw === "") {
      toast.error("Enter a monthly target");
      return;
    }
    const t = Number(raw);
    if (!Number.isFinite(t) || t < 0) {
      toast.error("Target must be a non-negative number");
      return;
    }
    setBusy(true);
    try {
      const month = summary?.month || thisMonthISO(tz);
      await api.put("/sales/targets", { month, target: t });
      toast.success("Monthly target saved");
      await reload();
    } catch (e) {
      toast.error(apiErrorMessage(e, "Could not save target"));
    } finally {
      setBusy(false);
    }
  };

  const openCreate = () => {
    setEditingId(null);
    setForm(emptyEntry());
    setAdding(true);
  };

  const openEdit = (entry) => {
    setEditingId(entry.id);
    setForm({
      buyer_name: entry.buyer_name || "",
      country: entry.country || "",
      product: entry.product || "",
      price: entry.price != null ? String(entry.price) : "",
      quantity: entry.quantity != null ? String(entry.quantity) : "",
      status: entry.status || "expected",
      expected_close_month: entry.expected_close_month || "",
      notes: entry.notes || "",
    });
    setAdding(true);
  };

  const closeForm = () => {
    if (busy) return;
    setAdding(false);
    setEditingId(null);
    setForm(emptyEntry());
  };

  const saveEntry = async () => {
    if (!form.buyer_name.trim() || !form.country.trim() || !form.product.trim()) {
      toast.error("Buyer, country, and product are required");
      return;
    }
    const price = Number(form.price);
    const quantity = Number(form.quantity);
    if (!Number.isFinite(price) || price < 0 || !Number.isFinite(quantity) || quantity <= 0) {
      toast.error("Enter a valid price and quantity");
      return;
    }
    const payload = {
      buyer_name: form.buyer_name.trim(),
      country: form.country.trim(),
      product: form.product.trim(),
      price,
      quantity,
      status: form.status,
      expected_close_month: form.expected_close_month.trim(),
      notes: form.notes.trim(),
    };
    setBusy(true);
    try {
      if (editingId) {
        await api.patch(`/sales/order-book/${editingId}`, payload);
        toast.success("Order book line updated");
      } else {
        await api.post("/sales/order-book", payload);
        toast.success("Order book line added");
      }
      closeForm();
      await reload();
    } catch (e) {
      toast.error(apiErrorMessage(e, editingId ? "Could not update entry" : "Could not create entry"));
    } finally {
      setBusy(false);
    }
  };

  const deleteEntry = async (id) => {
    setBusy(true);
    try {
      await api.delete(`/sales/order-book/${id}`);
      toast.success("Entry deleted");
      await reload();
    } catch (e) {
      toast.error(apiErrorMessage(e, "Could not delete"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div data-testid="sales-order-book" className="space-y-5">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3" data-testid="sales-target-card">
        <GlassCard className="p-4">
          <p className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">This month target</p>
          {tvs?.target_entered ? (
            <p className="font-mono text-2xl text-helm-fg mt-1">{money(tvs.target)}</p>
          ) : (
            <p className="font-mono text-xl text-helm-muted mt-1">No target set</p>
          )}
          {canManageTarget && (
            <div className="flex gap-2 mt-2">
              <input
                data-testid="sales-target-input"
                value={targetDraft}
                onChange={(e) => setTargetDraft(e.target.value)}
                placeholder="e.g. 5000000"
                className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-2 py-1.5 text-sm text-helm-fg font-mono"
              />
              <button
                type="button"
                disabled={busy}
                data-testid="sales-target-save"
                onClick={saveTarget}
                className="shrink-0 rounded-md border border-helm-line text-xs px-2 py-1.5 text-helm-fg hover:border-helm-gold/35"
              >
                Save
              </button>
            </div>
          )}
        </GlassCard>
        <GlassCard className="p-4">
          <p className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Confirmed actual</p>
          <p className="font-mono text-2xl text-helm-fg mt-1">{money(tvs?.actual || 0)}</p>
          <p className="text-[11px] text-helm-muted mt-0.5">
            {tvs?.target_entered
              ? `Gap ${money(tvs.gap)} · ${tvs.pct_of_target ?? "—"}% of target`
              : "Set a target to see the gap"}
          </p>
        </GlassCard>
        <GlassCard className="p-4">
          <p className="text-[10px] font-mono uppercase tracking-wide text-helm-muted">Confirmed / expected (month)</p>
          <p className="font-mono text-2xl text-helm-fg mt-1">
            {money(summary?.confirmed_this_month || 0)}
            <span className="text-helm-muted text-base"> / {money(summary?.expected_this_month || 0)}</span>
          </p>
        </GlassCard>
      </div>

      {(summary?.forward_pipeline || []).length > 0 && (
        <div data-testid="sales-forward-pipeline">
          <SectionLabel className="mb-2">Forward pipeline (next 3 months)</SectionLabel>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {summary.forward_pipeline.map((b) => (
              <div key={b.month} className="rounded-md border border-helm-line px-3 py-2.5">
                <p className="text-[10px] font-mono uppercase text-helm-muted">{b.month}</p>
                <p className="font-mono text-sm text-helm-fg mt-1">
                  Exp {money(b.expected)} · Neg {money(b.in_negotiation)} · Conf {money(b.confirmed)}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2 justify-between">
        <div className="flex flex-wrap gap-2">
          <select
            data-testid="order-book-filter-status"
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
            className="rounded-md border border-helm-line bg-helm-fg/[0.03] px-2 py-1.5 text-xs text-helm-fg"
          >
            <option value="">All statuses</option>
            <option value="confirmed">Confirmed</option>
            <option value="expected">Expected</option>
            <option value="in_negotiation">In negotiation</option>
          </select>
          <select
            data-testid="order-book-filter-country"
            value={filterCountry}
            onChange={(e) => setFilterCountry(e.target.value)}
            className="rounded-md border border-helm-line bg-helm-fg/[0.03] px-2 py-1.5 text-xs text-helm-fg"
          >
            <option value="">All countries</option>
            {countries.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        <button
          type="button"
          data-testid="add-order-book-btn"
          onClick={openCreate}
          className="inline-flex items-center gap-1.5 rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-3 py-2 hover:bg-helm-gold-hover"
        >
          <Plus className="w-4 h-4" /> Add line
        </button>
      </div>

      {visible.length === 0 ? (
        <EmptyState title="No order book lines" body="Add buyer / country / product lines to replace the external spreadsheet." />
      ) : (
        <div className="overflow-x-auto rounded-md border border-helm-line">
          <table className="w-full text-left text-sm" data-testid="order-book-table">
            <thead>
              <tr className="border-b border-helm-line text-[10px] font-mono uppercase tracking-wide text-helm-muted">
                <th className="px-3 py-2">Buyer</th>
                <th className="px-3 py-2">Country</th>
                <th className="px-3 py-2">Product</th>
                <th className="px-3 py-2">Price</th>
                <th className="px-3 py-2">Qty</th>
                <th className="px-3 py-2">Total</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">Expected close</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {visible.map((e) => (
                <tr key={e.id} className="border-b border-helm-line">
                  <td className="px-3 py-2 text-helm-fg">{e.buyer_name}</td>
                  <td className="px-3 py-2 text-helm-muted">{e.country}</td>
                  <td className="px-3 py-2 text-helm-muted">{e.product}</td>
                  <td className="px-3 py-2 font-mono text-xs">{money(e.price)}</td>
                  <td className="px-3 py-2 font-mono text-xs">{e.quantity}</td>
                  <td className="px-3 py-2 font-mono text-xs text-helm-fg">{money(e.total_value)}</td>
                  <td className="px-3 py-2 text-xs capitalize text-helm-muted">{(e.status || "").replace(/_/g, " ")}</td>
                  <td className="px-3 py-2 font-mono text-xs text-helm-muted">{formatCloseMonth(e.expected_close_month)}</td>
                  <td className="px-3 py-2">
                    {canMutate(e) && (
                      <div className="inline-flex items-center gap-1.5">
                        <CirEditBtn
                          disabled={busy}
                          onClick={() => openEdit(e)}
                          title="Edit entry"
                          data-testid={`edit-order-book-${e.id}`}
                        />
                        <CirDeleteBtn
                          disabled={busy}
                          onClick={() => deleteEntry(e.id)}
                          title="Delete entry"
                          data-testid={`delete-order-book-${e.id}`}
                        />
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {(summary?.by_country || []).length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <SectionLabel className="mb-2">By country</SectionLabel>
            <ul className="space-y-1 text-sm">
              {summary.by_country.slice(0, 8).map((r) => (
                <li key={r.country} className="flex justify-between text-helm-muted">
                  <span className="text-helm-fg">{r.country}</span>
                  <span className="font-mono">{money(r.total_value)} · {r.count}</span>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <SectionLabel className="mb-2">By product</SectionLabel>
            <ul className="space-y-1 text-sm">
              {summary.by_product.slice(0, 8).map((r) => (
                <li key={r.product} className="flex justify-between text-helm-muted">
                  <span className="text-helm-fg truncate max-w-[12rem]">{r.product}</span>
                  <span className="font-mono">{money(r.total_value)} · {r.count}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {adding && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-helm-ink/70" onClick={closeForm} />
          <div className="relative w-full max-w-md rounded-md border border-helm-line bg-helm-card p-5 space-y-3" data-testid="order-book-form">
            <div className="flex justify-between items-center">
              <p className="text-sm font-medium text-helm-fg">{editingId ? "Edit order book line" : "New order book line"}</p>
              <button type="button" onClick={closeForm} className="text-helm-muted"><X className="w-4 h-4" /></button>
            </div>
            {[
              ["buyer_name", "Buyer"],
              ["country", "Country"],
              ["product", "Product"],
            ].map(([key, label]) => (
              <label key={key} className="block space-y-1">
                <span className="text-[10px] font-mono uppercase text-helm-muted">{label}</span>
                <input
                  data-testid={`ob-${key}`}
                  value={form[key]}
                  onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
                  className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg"
                />
              </label>
            ))}
            <div className="grid grid-cols-2 gap-3">
              <label className="block space-y-1">
                <span className="text-[10px] font-mono uppercase text-helm-muted">Price</span>
                <input data-testid="ob-price" value={form.price} onChange={(e) => setForm((f) => ({ ...f, price: e.target.value }))} className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg" />
              </label>
              <label className="block space-y-1">
                <span className="text-[10px] font-mono uppercase text-helm-muted">Quantity</span>
                <input data-testid="ob-quantity" value={form.quantity} onChange={(e) => setForm((f) => ({ ...f, quantity: e.target.value }))} className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg" />
              </label>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <label className="block space-y-1">
                <span className="text-[10px] font-mono uppercase text-helm-muted">Status</span>
                <select data-testid="ob-status" value={form.status} onChange={(e) => setForm((f) => ({ ...f, status: e.target.value }))} className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg">
                  <option value="expected">Expected</option>
                  <option value="in_negotiation">In negotiation</option>
                  <option value="confirmed">Confirmed</option>
                </select>
              </label>
              <label className="block space-y-1">
                <span className="text-[10px] font-mono uppercase text-helm-muted">Expected closing month</span>
                <select
                  data-testid="ob-month"
                  value={form.expected_close_month}
                  onChange={(e) => setForm((f) => ({ ...f, expected_close_month: e.target.value }))}
                  className="w-full rounded-md border border-helm-line bg-helm-fg/[0.03] px-3 py-2 text-sm text-helm-fg"
                >
                  <option value="">Select month…</option>
                  {monthSelectOptions.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </label>
            </div>
            <button type="button" disabled={busy} data-testid="ob-submit" onClick={saveEntry} className="w-full rounded-md bg-helm-gold text-helm-navy font-medium text-sm py-2 hover:bg-helm-gold-hover disabled:opacity-50">
              {editingId ? "Save changes" : "Save line"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
