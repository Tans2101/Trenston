import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { Check, Copy, KeyRound } from "lucide-react";
import { api } from "@/lib/api";
import { GlassCard } from "@/components/kit";
import { confirmAction } from "@/components/ConfirmHost";

const MCP_DOCS_URL = "https://github.com/Tans2101/Trenston/tree/main/mcp-server";

function detailMessage(e, fallback) {
  const d = e?.response?.data?.detail;
  if (typeof d === "string") return d;
  if (d && typeof d.message === "string") return d.message;
  return fallback;
}

function formatDate(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

/**
 * Personal API keys for the read-only public API and the MCP server.
 * A key reads exactly what its owner can see in the app, and nothing else.
 */
export default function ApiKeysSettings({ canBilling = false }) {
  const [state, setState] = useState({ loading: true, keys: [], allowed: false, planMessage: null, maxKeys: 10 });
  const [name, setName] = useState("");
  const [creating, setCreating] = useState(false);
  const [revokingId, setRevokingId] = useState(null);
  const [newKey, setNewKey] = useState(null);
  const [copied, setCopied] = useState(false);
  const [grants, setGrants] = useState([]);
  const [disconnectingId, setDisconnectingId] = useState(null);

  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/api-keys");
      setState({
        loading: false,
        keys: data?.keys || [],
        allowed: !!data?.allowed,
        planMessage: data?.plan_message || null,
        maxKeys: data?.max_keys || 10,
      });
    } catch (e) {
      setState((s) => ({ ...s, loading: false }));
      toast.error(detailMessage(e, "Could not load your API keys. Please try again."));
    }
  }, []);

  const loadGrants = useCallback(async () => {
    try {
      const { data } = await api.get("/oauth/grants");
      setGrants(data?.grants || []);
    } catch {
      setGrants([]);
    }
  }, []);

  useEffect(() => {
    load();
    loadGrants();
  }, [load, loadGrants]);

  const disconnect = async (grant) => {
    if (!(await confirmAction({
      title: `Disconnect ${grant.client_name}?`,
      description: "It loses access to this workspace right away. You can connect it again from the assistant.",
      confirmLabel: "Disconnect",
      destructive: true,
    }))) return;
    setDisconnectingId(grant.id);
    try {
      await api.delete(`/oauth/grants/${grant.id}`);
      toast.success(`${grant.client_name} disconnected`);
      await loadGrants();
    } catch (e) {
      toast.error(detailMessage(e, "Could not disconnect. Please try again."));
    } finally {
      setDisconnectingId(null);
    }
  };

  const create = async (event) => {
    event?.preventDefault();
    if (creating) return;
    setCreating(true);
    try {
      const { data } = await api.post("/api-keys", { name: name.trim() || undefined });
      setNewKey(data);
      setCopied(false);
      setName("");
      await load();
    } catch (e) {
      toast.error(detailMessage(e, "Could not create the key. Please try again."));
    } finally {
      setCreating(false);
    }
  };

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(newKey?.key || "");
      setCopied(true);
      toast.success("Key copied");
    } catch {
      toast.error("Could not copy. Select the key and copy it manually.");
    }
  };

  const revoke = async (key) => {
    if (!(await confirmAction({
      title: `Revoke "${key.name}"?`,
      description: "Anything using this key stops working right away. This cannot be undone.",
      confirmLabel: "Revoke",
      destructive: true,
    }))) return;
    setRevokingId(key.id);
    try {
      await api.delete(`/api-keys/${key.id}`);
      if (newKey?.id === key.id) setNewKey(null);
      toast.success("Key revoked");
      await load();
    } catch (e) {
      toast.error(detailMessage(e, "Could not revoke the key. Please try again."));
    } finally {
      setRevokingId(null);
    }
  };

  const atLimit = state.keys.length >= state.maxKeys;
  const apiBase = `${window.location.origin}/api/v1`;

  return (
    <GlassCard id="api-keys" className="p-5 mb-4 fade-up scroll-mt-24" data-testid="api-keys-card">
      <div className="flex items-center gap-1.5 mb-2 text-helm-gold">
        <KeyRound className="w-4 h-4" />
        <span className="font-mono text-[11px] uppercase tracking-[0.2em]">API keys</span>
      </div>
      <p className="text-sm text-helm-muted mb-4 leading-relaxed">
        Let AI assistants and scripts read this workspace as you. A key can read, never change anything, and it
        sees exactly what you can see in Trenston.
      </p>

      {state.loading ? (
        <p className="text-sm text-helm-muted" data-testid="api-keys-loading">Loading…</p>
      ) : !state.allowed ? (
        <div data-testid="api-keys-plan-gate">
          <p className="text-sm text-helm-fg">{state.planMessage || "API access is not available on your plan."}</p>
          {canBilling ? (
            <a
              href="/app/billing"
              className="mt-3 inline-flex items-center text-sm text-helm-gold hover:text-helm-gold-hover"
              data-testid="api-keys-upgrade-link"
            >
              See plans →
            </a>
          ) : (
            <p className="mt-2 text-sm text-helm-muted">Ask your workspace owner about upgrading.</p>
          )}
        </div>
      ) : (
        <>
          {grants.length > 0 && (
            <div className="mb-5" data-testid="oauth-grants">
              <p className="mb-2 text-xs font-medium uppercase tracking-[0.14em] text-helm-muted">Connected apps</p>
              <ul className="divide-y divide-helm-line border-y border-helm-line">
                {grants.map((g) => (
                  <li key={g.id} className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:justify-between">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-helm-fg">{g.client_name}</p>
                      <p className="mt-0.5 text-xs text-helm-muted">
                        Read-only{" · "}
                        {formatDate(g.created_at) ? `Connected ${formatDate(g.created_at)}` : "Connected recently"}
                        {formatDate(g.last_used_at) ? ` · Last active ${formatDate(g.last_used_at)}` : ""}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => disconnect(g)}
                      disabled={disconnectingId === g.id}
                      className="self-start rounded-md border border-helm-line px-3 py-1.5 text-sm text-helm-fg hover:bg-helm-fg/5 disabled:opacity-60 sm:self-auto"
                      data-testid={`oauth-grant-disconnect-${g.id}`}
                    >
                      {disconnectingId === g.id ? "Disconnecting…" : "Disconnect"}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {newKey?.key && (
            <div className="mb-4 rounded-md border border-helm-gold/40 bg-helm-gold/10 p-4" data-testid="api-key-reveal">
              <p className="text-sm font-medium text-helm-fg">Copy your new key now. You won't see it again.</p>
              <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center">
                <code
                  className="min-w-0 flex-1 break-all rounded border border-helm-line bg-helm-bg px-3 py-2 font-mono text-xs text-helm-fg"
                  data-testid="api-key-value"
                >
                  {newKey.key}
                </code>
                <button
                  type="button"
                  onClick={copy}
                  className="inline-flex items-center justify-center gap-1.5 rounded-md bg-helm-gold px-3.5 py-2 text-sm font-medium text-helm-navy hover:bg-helm-gold-hover"
                  data-testid="api-key-copy"
                >
                  {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                  {copied ? "Copied" : "Copy"}
                </button>
              </div>
              <button
                type="button"
                onClick={() => setNewKey(null)}
                className="mt-3 text-xs text-helm-muted hover:text-helm-fg"
                data-testid="api-key-reveal-done"
              >
                I've saved it
              </button>
            </div>
          )}

          {state.keys.length > 0 ? (
            <ul className="mb-4 divide-y divide-helm-line border-y border-helm-line" data-testid="api-keys-list">
              {state.keys.map((k) => (
                <li key={k.id} className="flex flex-col gap-2 py-3 sm:flex-row sm:items-center sm:justify-between">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-helm-fg">{k.name}</p>
                    <p className="mt-0.5 font-mono text-xs text-helm-muted">
                      {k.hint}
                      {" · "}
                      {formatDate(k.created_at) ? `Created ${formatDate(k.created_at)}` : "Created recently"}
                      {" · "}
                      {formatDate(k.last_used_at) ? `Last used ${formatDate(k.last_used_at)}` : "Never used"}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => revoke(k)}
                    disabled={revokingId === k.id}
                    className="self-start rounded-md border border-helm-line px-3 py-1.5 text-sm text-helm-fg hover:bg-helm-fg/5 disabled:opacity-60 sm:self-auto"
                    data-testid={`api-key-revoke-${k.id}`}
                  >
                    {revokingId === k.id ? "Revoking…" : "Revoke"}
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mb-4 text-sm text-helm-muted" data-testid="api-keys-empty">No keys yet.</p>
          )}

          <form onSubmit={create} className="flex flex-col gap-2 sm:flex-row" data-testid="api-key-create-form">
            <label htmlFor="api-key-name" className="sr-only">Key name</label>
            <input
              id="api-key-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={60}
              placeholder="Name, e.g. My AI assistant"
              disabled={atLimit}
              className="min-w-0 flex-1 rounded-md border border-helm-line bg-transparent px-3 py-2 text-sm text-helm-fg placeholder:text-helm-muted focus:border-helm-gold focus:outline-none disabled:opacity-60"
              data-testid="api-key-name-input"
            />
            <button
              type="submit"
              disabled={creating || atLimit}
              className="rounded-md bg-helm-gold px-4 py-2 text-sm font-medium text-helm-navy transition-colors hover:bg-helm-gold-hover disabled:opacity-60"
              data-testid="api-key-create"
            >
              {creating ? "Creating…" : "Create key"}
            </button>
          </form>
          {atLimit && (
            <p className="mt-2 text-xs text-helm-muted">You have the maximum of {state.maxKeys} keys. Revoke one to create another.</p>
          )}

          <details className="mt-4 text-sm text-helm-muted" data-testid="api-keys-howto">
            <summary className="cursor-pointer text-helm-fg">How to use a key</summary>
            <div className="mt-3 space-y-3 leading-relaxed">
              <p>
                Send it as a header: <code className="font-mono text-xs text-helm-fg">Authorization: Bearer trn_…</code>
              </p>
              <p>
                API base: <code className="break-all font-mono text-xs text-helm-fg">{apiBase}</code>. Read-only
                endpoints: <code className="font-mono text-xs text-helm-fg">me</code>,{" "}
                <code className="font-mono text-xs text-helm-fg">briefing</code>,{" "}
                <code className="font-mono text-xs text-helm-fg">decisions</code>,{" "}
                <code className="font-mono text-xs text-helm-fg">tasks</code>,{" "}
                <code className="font-mono text-xs text-helm-fg">my-work</code>,{" "}
                <code className="font-mono text-xs text-helm-fg">financials</code>.
              </p>
              <p>
                In Claude, add a custom connector with the URL{" "}
                <code className="break-all font-mono text-xs text-helm-fg">https://trenston-mcp.onrender.com/mcp</code>{" "}
                and sign in. No key needed: it appears above under Connected apps.
              </p>
              <p>
                For other AI assistants that support MCP, use the{" "}
                <a href={MCP_DOCS_URL} target="_blank" rel="noreferrer" className="text-helm-gold hover:text-helm-gold-hover">
                  Trenston MCP server
                </a>{" "}
                with this key.
              </p>
            </div>
          </details>
        </>
      )}
    </GlassCard>
  );
}
