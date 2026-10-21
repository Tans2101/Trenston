import { useEffect, useMemo, useState } from "react";
import {
  ArrowDown, ArrowLeft, ArrowUp, Eye, Inbox, Mail, Plus, Save, Search, Trash2, UserPlus,
} from "lucide-react";
import { toast } from "sonner";
import { AppPageHeader, EmptyState, ErrorScreen, GlassCard, ListLabel, Spinner } from "@/components/kit";
import { useFetch } from "@/hooks/useFetch";
import { api, apiErrorMessage } from "@/lib/api";
import { confirmAction } from "@/components/ConfirmHost";
import { cn } from "@/lib/utils";
import WidgetGrid from "@/components/custom/WidgetGrid";

/**
 * Trenston operator tool for the custom-dashboard service.
 * Only the operator email (ANALYTICS_ADMIN_EMAIL on the API) can load any of this.
 */

const PACKS = [
  ["member", "Member"],
  ["exec", "Executive"],
  ["finance", "Finance"],
  ["hr", "People/HR"],
  ["sales", "Sales"],
  ["ops", "Operations"],
];

const input = "w-full rounded-md border border-helm-line bg-helm-bg px-3 py-2 text-sm text-helm-fg placeholder:text-helm-muted focus:outline-none focus:ring-2 focus:ring-helm-gold/40";
const label = "mb-1 block text-xs font-medium text-helm-muted";
const btn = "inline-flex items-center gap-1.5 rounded-md px-3 py-2 text-sm font-medium transition-colors disabled:opacity-50";
const btnPrimary = cn(btn, "bg-helm-gold text-helm-navy hover:bg-helm-gold-hover");
const btnGhost = cn(btn, "border border-helm-line text-helm-fg hover:bg-helm-navy/5");

function errText(err) {
  return apiErrorMessage(err?.response?.data?.detail || err, "That did not work");
}

function fmtDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

// ---------------------------------------------------------------- inquiries

function InquiryRow({ row, catalog, onChanged, onSetUp }) {
  const [notes, setNotes] = useState(row.notes || "");
  const save = async (patch) => {
    try {
      await api.patch(`/admin/custom/inquiries/${row.inquiry_id}`, patch);
      onChanged();
    } catch (err) {
      toast.error(errText(err));
    }
  };
  return (
    <GlassCard className="p-5" data-testid={`inquiry-${row.inquiry_id}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-base font-semibold text-helm-fg">{row.company}</p>
          <p className="text-sm text-helm-muted">
            {row.name}{row.role ? `, ${row.role}` : ""} ·{" "}
            <a className="text-helm-gold hover:underline" href={`mailto:${row.email}`}>{row.email}</a>
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs text-helm-muted">{fmtDate(row.created_at)}</span>
          <select
            className={cn(input, "w-auto py-1.5")}
            value={row.status}
            onChange={(e) => save({ status: e.target.value })}
            aria-label="Inquiry status"
          >
            {(catalog?.inquiry_statuses || []).map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
      </div>
      <div className="mt-3 flex flex-wrap gap-2 text-xs">
        {row.company_size ? <span className="rounded-full border border-helm-line px-2 py-0.5 text-helm-muted">{catalog?.company_size_labels?.[row.company_size]}</span> : null}
        {row.budget_range ? <span className="rounded-full border border-helm-gold/40 px-2 py-0.5 text-helm-fg">Budget: {catalog?.budget_labels?.[row.budget_range]}</span> : null}
        {row.workspace_id ? <span className="rounded-full bg-helm-gold/15 px-2 py-0.5 text-helm-fg">Client created</span> : null}
      </div>
      {row.tools ? <p className="mt-3 text-sm text-helm-muted"><span className="text-helm-fg">Tools:</span> {row.tools}</p> : null}
      <p className="mt-2 whitespace-pre-wrap text-sm text-helm-fg">{row.needs}</p>
      <textarea
        className={cn(input, "mt-3 min-h-[60px]")}
        placeholder="Your notes (call summary, quote sent, next step)"
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        onBlur={() => notes !== (row.notes || "") && save({ notes })}
      />
      {!row.workspace_id ? (
        <div className="mt-3 flex justify-end">
          <button type="button" className={btnGhost} onClick={() => onSetUp(row)}>
            <UserPlus className="h-4 w-4" /> Set up as client
          </button>
        </div>
      ) : null}
    </GlassCard>
  );
}

function Inquiries({ catalog, onSetUp }) {
  const { data, loading, error, reload } = useFetch("/admin/custom/inquiries");
  if (loading && !data) return <Spinner className="h-5 w-5" />;
  if (error) return <ErrorScreen label="Inquiries" message={errText(error)} onRetry={reload} />;
  const rows = data?.inquiries || [];
  if (!rows.length) {
    return <EmptyState icon={Inbox} title="No inquiries yet" body="Requests from trenston.com/custom land here and in your inbox." />;
  }
  return (
    <div className="space-y-3">
      {rows.map((row) => (
        <InquiryRow key={row.inquiry_id} row={row} catalog={catalog} onChanged={reload} onSetUp={onSetUp} />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------- new / convert client

function NewClient({ catalog, prefill, onCreated }) {
  const [form, setForm] = useState({ company_name: "", owner_email: "", tier: "configured", send_invite: true });
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (prefill) {
      setForm((f) => ({ ...f, company_name: prefill.company || "", owner_email: prefill.email || "", inquiry_id: prefill.inquiry_id }));
    }
  }, [prefill]);
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { data } = await api.post("/admin/custom/workspaces", form);
      toast.success(data.owner?.email_sent ? "Client created and invite sent" : "Client created");
      onCreated(data.workspace_id);
    } catch (err) {
      toast.error(errText(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <GlassCard className="p-5">
      <ListLabel className="mb-4">New client company</ListLabel>
      <form onSubmit={submit} className="grid gap-3 sm:grid-cols-2">
        <div>
          <label className={label} htmlFor="nc-company">Company name</label>
          <input id="nc-company" className={input} required maxLength={120} value={form.company_name}
            onChange={(e) => setForm({ ...form, company_name: e.target.value })} />
        </div>
        <div>
          <label className={label} htmlFor="nc-email">Owner email (approved)</label>
          <input id="nc-email" className={input} type="email" required value={form.owner_email}
            onChange={(e) => setForm({ ...form, owner_email: e.target.value })} />
        </div>
        <div>
          <label className={label} htmlFor="nc-tier">Tier</label>
          <select id="nc-tier" className={input} value={form.tier} onChange={(e) => setForm({ ...form, tier: e.target.value })}>
            {(catalog?.tiers || []).map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
          </select>
        </div>
        <label className="flex items-center gap-2 self-end pb-2 text-sm text-helm-fg">
          <input type="checkbox" checked={form.send_invite} onChange={(e) => setForm({ ...form, send_invite: e.target.checked })} />
          Email the owner an invite now
        </label>
        <p className="text-xs text-helm-muted sm:col-span-2">
          Creates their company on the Business plan with custom billing (you invoice them). The owner joins when they sign in with this email.
        </p>
        <div className="sm:col-span-2">
          <button type="submit" className={btnPrimary} disabled={busy}><Plus className="h-4 w-4" /> Create client</button>
        </div>
      </form>
    </GlassCard>
  );
}

function ConvertExisting({ onEnabled }) {
  const [email, setEmail] = useState("");
  const [rows, setRows] = useState(null);
  const [customBilling, setCustomBilling] = useState(true);
  const lookup = async (e) => {
    e.preventDefault();
    try {
      const { data } = await api.get("/admin/custom/lookup", { params: { email } });
      setRows(data.workspaces || []);
    } catch (err) {
      toast.error(errText(err));
    }
  };
  const enable = async (ws) => {
    try {
      await api.post(`/admin/custom/workspaces/${ws.workspace_id}/enable`, { tier: "configured", custom_billing: customBilling });
      toast.success(`${ws.name} is now a custom client`);
      onEnabled(ws.workspace_id);
    } catch (err) {
      toast.error(errText(err));
    }
  };
  return (
    <GlassCard className="p-5">
      <ListLabel className="mb-4">Existing Trenston company</ListLabel>
      <form onSubmit={lookup} className="flex gap-2">
        <input className={input} type="email" required placeholder="Owner's email" value={email} onChange={(e) => setEmail(e.target.value)} />
        <button type="submit" className={btnGhost}><Search className="h-4 w-4" /> Find</button>
      </form>
      <label className="mt-3 flex items-center gap-2 text-sm text-helm-fg">
        <input type="checkbox" checked={customBilling} onChange={(e) => setCustomBilling(e.target.checked)} />
        Switch them to custom billing (Business plan, invoiced by you)
      </label>
      {rows ? (
        <ul className="mt-3 divide-y divide-helm-line">
          {rows.length === 0 ? <li className="py-2 text-sm text-helm-muted">No companies owned by that email.</li> : null}
          {rows.map((ws) => (
            <li key={ws.workspace_id} className="flex items-center justify-between gap-3 py-2 text-sm">
              <span className="min-w-0 truncate text-helm-fg">
                {ws.name} <span className="text-helm-muted">· {ws.plan}{ws.has_paddle ? " · pays via Paddle" : ""}</span>
              </span>
              <button type="button" className={btnGhost} onClick={() => enable(ws)}>
                {ws.enabled ? "Open" : "Make custom client"}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </GlassCard>
  );
}

// ---------------------------------------------------------------- widget editor

const BLANK_PARAMS = {
  financial_kpi: { metric: "cash" },
  revenue_expenses_chart: { months: 6 },
  tasks_summary: { limit: 5 },
  decisions_open: { limit: 5 },
  briefing_headline: {},
  manual_kpi: { value: "", target: "", caption: "", tone: "neutral" },
  manual_table: { columns: ["Item", "Value"], rows: [] },
  note: { body: "" },
  custom: { component: "", props: {} },
};

function ParamsEditor({ widget, catalog, onChange }) {
  const p = widget.params || {};
  const set = (patch) => onChange({ ...widget, params: { ...p, ...patch } });
  const [propsText, setPropsText] = useState(JSON.stringify(p.props || {}, null, 2));
  switch (widget.type) {
    case "financial_kpi":
      return (
        <select className={input} value={p.metric} onChange={(e) => set({ metric: e.target.value })} aria-label="Figure">
          {(catalog?.financial_metrics || []).map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
        </select>
      );
    case "revenue_expenses_chart":
      return (
        <label className="text-xs text-helm-muted">Months
          <input className={input} type="number" min={3} max={24} value={p.months ?? 6} onChange={(e) => set({ months: Number(e.target.value) })} />
        </label>
      );
    case "tasks_summary":
    case "decisions_open":
      return (
        <label className="text-xs text-helm-muted">Rows to list (0 shows counts only)
          <input className={input} type="number" min={0} max={20} value={p.limit ?? 5} onChange={(e) => set({ limit: Number(e.target.value) })} />
        </label>
      );
    case "manual_kpi":
      return (
        <div className="grid gap-2 sm:grid-cols-2">
          <input className={input} placeholder="Value, e.g. 1,240 units" value={p.value || ""} onChange={(e) => set({ value: e.target.value })} />
          <input className={input} placeholder="Target (optional)" value={p.target || ""} onChange={(e) => set({ target: e.target.value })} />
          <input className={input} placeholder="Caption (optional)" value={p.caption || ""} onChange={(e) => set({ caption: e.target.value })} />
          <select className={input} value={p.tone || "neutral"} onChange={(e) => set({ tone: e.target.value })} aria-label="Tone">
            {(catalog?.tones || []).map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
      );
    case "manual_table":
      return (
        <div className="grid gap-2">
          <input className={input} placeholder="Columns, separated by commas" value={(p.columns || []).join(", ")}
            onChange={(e) => set({ columns: e.target.value.split(",").map((c) => c.trim()).filter(Boolean) })} />
          <textarea className={cn(input, "min-h-[90px] font-mono text-xs")} placeholder="One row per line, cells separated by |"
            value={(p.rows || []).map((r) => r.join(" | ")).join("\n")}
            onChange={(e) => set({ rows: e.target.value.split("\n").filter((l) => l.trim()).map((l) => l.split("|").map((c) => c.trim())) })} />
        </div>
      );
    case "note":
      return <textarea className={cn(input, "min-h-[80px]")} value={p.body || ""} onChange={(e) => set({ body: e.target.value })} />;
    case "custom":
      return (
        <div className="grid gap-2">
          <input className={input} placeholder="Component id, e.g. acme-line-map" value={p.component || ""} onChange={(e) => set({ component: e.target.value })} />
          <textarea
            className={cn(input, "min-h-[80px] font-mono text-xs")}
            value={propsText}
            onChange={(e) => {
              setPropsText(e.target.value);
              try { set({ props: JSON.parse(e.target.value || "{}") }); } catch { /* keep typing */ }
            }}
            aria-label="Component props (JSON)"
          />
          <p className="text-xs text-helm-muted">Register the component in src/components/custom/bespoke.js.</p>
        </div>
      );
    default:
      return null;
  }
}

function WidgetEditor({ widgets, setWidgets, catalog }) {
  const move = (i, d) => {
    const next = [...widgets];
    const j = i + d;
    if (j < 0 || j >= next.length) return;
    [next[i], next[j]] = [next[j], next[i]];
    setWidgets(next);
  };
  const update = (i, w) => setWidgets(widgets.map((x, k) => (k === i ? w : x)));
  const add = (type) => setWidgets([...widgets, { id: `w_${Math.random().toString(36).slice(2, 10)}`, type, title: "", width: 1, params: { ...BLANK_PARAMS[type] } }]);
  return (
    <div className="space-y-3">
      {widgets.map((w, i) => (
        <div key={w.id} className="rounded-lg border border-helm-line p-3" data-testid={`editor-widget-${i}`}>
          <div className="flex flex-wrap items-center gap-2">
            <select className={cn(input, "w-auto")} value={w.type} aria-label="Widget type"
              onChange={(e) => update(i, { ...w, type: e.target.value, params: { ...BLANK_PARAMS[e.target.value] } })}>
              {(catalog?.widget_types || []).map((t) => <option key={t.type} value={t.type}>{t.label}</option>)}
            </select>
            <input className={cn(input, "min-w-[160px] flex-1")} placeholder="Title (optional)" value={w.title || ""}
              onChange={(e) => update(i, { ...w, title: e.target.value })} />
            <select className={cn(input, "w-auto")} value={w.width || 1} aria-label="Width"
              onChange={(e) => update(i, { ...w, width: Number(e.target.value) })}>
              <option value={1}>1/3 width</option>
              <option value={2}>2/3 width</option>
              <option value={3}>Full width</option>
            </select>
            <button type="button" className={btnGhost} onClick={() => move(i, -1)} aria-label="Move up"><ArrowUp className="h-4 w-4" /></button>
            <button type="button" className={btnGhost} onClick={() => move(i, 1)} aria-label="Move down"><ArrowDown className="h-4 w-4" /></button>
            <button type="button" className={btnGhost} onClick={() => setWidgets(widgets.filter((_, k) => k !== i))} aria-label="Remove widget"><Trash2 className="h-4 w-4" /></button>
          </div>
          <div className="mt-2"><ParamsEditor key={`${w.id}-${w.type}`} widget={w} catalog={catalog} onChange={(nw) => update(i, nw)} /></div>
        </div>
      ))}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-helm-muted">Add:</span>
        {(catalog?.widget_types || []).map((t) => (
          <button key={t.type} type="button" className={cn(btnGhost, "py-1 text-xs")} onClick={() => add(t.type)}>
            <Plus className="h-3 w-3" /> {t.label}
          </button>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- client detail

function ApprovedEmails({ wsId, config, members, onChanged }) {
  const [email, setEmail] = useState("");
  const [pack, setPack] = useState("member");
  const [busy, setBusy] = useState(false);
  const statusByEmail = useMemo(() => Object.fromEntries((members || []).map((m) => [m.email, m])), [members]);
  const add = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const { data } = await api.post(`/admin/custom/workspaces/${wsId}/approved-emails`, { email, pack, send_invite: true });
      toast.success(data.already_member ? "Approved (already in the company)" : data.email_sent ? "Approved and invited" : "Approved");
      setEmail("");
      onChanged();
    } catch (err) {
      toast.error(errText(err));
    } finally {
      setBusy(false);
    }
  };
  const remove = async (addr) => {
    const ok = await confirmAction({
      title: `Remove ${addr}?`,
      description: "They lose access to this company in Trenston. A pending invite is cancelled.",
      confirmLabel: "Remove access",
      destructive: true,
    });
    if (!ok) return;
    try {
      await api.delete(`/admin/custom/workspaces/${wsId}/approved-emails/${encodeURIComponent(addr)}`);
      onChanged();
    } catch (err) {
      toast.error(errText(err));
    }
  };
  return (
    <div>
      <ul className="divide-y divide-helm-line">
        {(config.approved_emails || []).map((addr) => {
          const m = statusByEmail[addr];
          return (
            <li key={addr} className="flex items-center justify-between gap-3 py-2 text-sm">
              <span className="min-w-0 truncate text-helm-fg"><Mail className="mr-1.5 inline h-3.5 w-3.5 text-helm-muted" />{addr}</span>
              <span className="flex items-center gap-2">
                <span className="font-mono text-xs text-helm-muted">
                  {m ? `${m.pack} · ${m.status === "active" ? "joined" : "invited"}` : "not in company"}
                </span>
                {m?.pack !== "owner" ? (
                  <button type="button" className="text-helm-muted hover:text-red-600" onClick={() => remove(addr)} aria-label={`Remove ${addr}`}>
                    <Trash2 className="h-4 w-4" />
                  </button>
                ) : null}
              </span>
            </li>
          );
        })}
      </ul>
      <form onSubmit={add} className="mt-3 flex flex-wrap gap-2">
        <input className={cn(input, "min-w-[200px] flex-1")} type="email" required placeholder="name@client.com" value={email} onChange={(e) => setEmail(e.target.value)} />
        <select className={cn(input, "w-auto")} value={pack} onChange={(e) => setPack(e.target.value)} aria-label="Access">
          {PACKS.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
        </select>
        <button type="submit" className={btnPrimary} disabled={busy}><UserPlus className="h-4 w-4" /> Approve and invite</button>
      </form>
    </div>
  );
}

function ClientDetail({ wsId, catalog, onBack }) {
  const { data, loading, error, reload } = useFetch(`/admin/custom/workspaces/${wsId}`);
  const [draft, setDraft] = useState(null);
  const [preview, setPreview] = useState(null);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    if (data?.config) {
      const c = data.config;
      setDraft({
        title: c.title || "", subtitle: c.subtitle || "", tier: c.tier || "configured",
        enabled: Boolean(c.enabled), restrict_to_approved: Boolean(c.restrict_to_approved),
        widgets: c.widgets || [],
      });
    }
  }, [data]);
  if (loading && !data) return <Spinner className="h-5 w-5" />;
  if (error) return <ErrorScreen label="Client" message={errText(error)} onRetry={reload} />;
  if (!draft) return null;

  const runPreview = async () => {
    try {
      const { data: out } = await api.post("/admin/custom/preview", { widgets: draft.widgets });
      setPreview(out.widgets);
    } catch (err) {
      toast.error(errText(err));
    }
  };
  const save = async () => {
    setSaving(true);
    try {
      await api.put(`/admin/custom/workspaces/${wsId}/config`, draft);
      toast.success("Saved. The client sees it on their next refresh.");
      reload();
    } catch (err) {
      toast.error(errText(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-5">
      <button type="button" className={btnGhost} onClick={onBack}><ArrowLeft className="h-4 w-4" /> All clients</button>
      <GlassCard className="p-5">
        <ListLabel className="mb-4">{data.name}</ListLabel>
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label className={label} htmlFor="cd-title">Dashboard title (shown in their sidebar)</label>
            <input id="cd-title" className={input} maxLength={120} value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
          </div>
          <div>
            <label className={label} htmlFor="cd-tier">Tier</label>
            <select id="cd-tier" className={input} value={draft.tier} onChange={(e) => setDraft({ ...draft, tier: e.target.value })}>
              {(catalog?.tiers || []).map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
            </select>
          </div>
          <div className="sm:col-span-2">
            <label className={label} htmlFor="cd-sub">Subtitle</label>
            <input id="cd-sub" className={input} maxLength={240} value={draft.subtitle} onChange={(e) => setDraft({ ...draft, subtitle: e.target.value })} />
          </div>
          <label className="flex items-center gap-2 text-sm text-helm-fg">
            <input type="checkbox" checked={draft.enabled} onChange={(e) => setDraft({ ...draft, enabled: e.target.checked })} />
            Dashboard is live for the client
          </label>
          <label className="flex items-center gap-2 text-sm text-helm-fg">
            <input type="checkbox" checked={draft.restrict_to_approved} onChange={(e) => setDraft({ ...draft, restrict_to_approved: e.target.checked })} />
            Only approved emails can see it (owner always can)
          </label>
        </div>
        <p className="mt-3 font-mono text-xs text-helm-muted">
          {data.plan} plan · {data.billing_source === "custom" ? "custom billing" : "billed via Paddle"} · {data.owner_joined ? "owner has joined" : "owner has not signed in yet"}
        </p>
      </GlassCard>

      <GlassCard className="p-5">
        <ListLabel className="mb-4" count={(data.config.approved_emails || []).length}>Approved emails</ListLabel>
        <ApprovedEmails wsId={wsId} config={data.config} members={data.members} onChanged={reload} />
      </GlassCard>

      <GlassCard className="p-5">
        <ListLabel className="mb-4" count={draft.widgets.length}>Widgets</ListLabel>
        <WidgetEditor widgets={draft.widgets} setWidgets={(w) => setDraft({ ...draft, widgets: w })} catalog={catalog} />
        <div className="mt-5 flex flex-wrap gap-2">
          <button type="button" className={btnPrimary} onClick={save} disabled={saving}><Save className="h-4 w-4" /> Save</button>
          <button type="button" className={btnGhost} onClick={runPreview}><Eye className="h-4 w-4" /> Preview with sample data</button>
        </div>
      </GlassCard>

      {preview ? (
        <div>
          <ListLabel className="mb-4">Preview (sample data, not the client's)</ListLabel>
          <WidgetGrid widgets={preview} />
        </div>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------- page

function ClientList({ onOpen }) {
  const { data, loading, error, reload } = useFetch("/admin/custom/workspaces");
  if (loading && !data) return <Spinner className="h-5 w-5" />;
  if (error) return <ErrorScreen label="Clients" message={errText(error)} onRetry={reload} />;
  const rows = data?.workspaces || [];
  if (!rows.length) return <p className="text-sm text-helm-muted">No custom clients yet.</p>;
  return (
    <ul className="divide-y divide-helm-line rounded-xl border border-helm-line bg-helm-card">
      {rows.map((ws) => (
        <li key={ws.workspace_id}>
          <button type="button" onClick={() => onOpen(ws.workspace_id)}
            className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left hover:bg-helm-navy/5">
            <span className="min-w-0">
              <span className="block truncate text-sm font-medium text-helm-fg">{ws.name}</span>
              <span className="block text-xs text-helm-muted">{ws.title} · {ws.tier} · {ws.widget_count} widgets · {ws.approved_count} approved</span>
            </span>
            <span className={cn("shrink-0 rounded-full px-2 py-0.5 text-xs", ws.enabled ? "bg-helm-gold/15 text-helm-fg" : "border border-helm-line text-helm-muted")}>
              {ws.enabled ? "Live" : "Off"}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}

export default function CustomClients() {
  const catalogQ = useFetch("/admin/custom/catalog");
  const [tab, setTab] = useState("inquiries");
  const [openId, setOpenId] = useState(null);
  const [prefill, setPrefill] = useState(null);

  if (catalogQ.error) {
    return <ErrorScreen label="Custom clients" message="This page is only for the Trenston operator." />;
  }
  const catalog = catalogQ.data;
  const open = (id) => { setOpenId(id); setTab("clients"); };

  return (
    <div data-testid="custom-clients">
      <AppPageHeader title="Custom clients" subtitle="Inquiries from trenston.com/custom and the companies you build dashboards for." />
      {openId ? (
        <ClientDetail wsId={openId} catalog={catalog} onBack={() => setOpenId(null)} />
      ) : (
        <>
          <div className="mb-5 flex gap-2" role="tablist">
            {[["inquiries", "Inquiries"], ["clients", "Clients"]].map(([id, name]) => (
              <button key={id} type="button" role="tab" aria-selected={tab === id} onClick={() => setTab(id)}
                className={cn(btn, tab === id ? "bg-helm-navy/10 text-helm-fg" : "text-helm-muted hover:text-helm-fg")}>
                {name}
              </button>
            ))}
          </div>
          {tab === "inquiries" ? (
            <Inquiries catalog={catalog} onSetUp={(row) => { setPrefill(row); setTab("clients"); }} />
          ) : (
            <div className="space-y-5">
              <div className="grid gap-5 lg:grid-cols-2">
                <NewClient catalog={catalog} prefill={prefill} onCreated={open} />
                <ConvertExisting onEnabled={open} />
              </div>
              <ClientList onOpen={setOpenId} />
            </div>
          )}
        </>
      )}
    </div>
  );
}
