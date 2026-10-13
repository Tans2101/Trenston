import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";

const MIN_CHARS = 2;
const WAIT_MS = 220;

/**
 * Looks up the person's own tasks, decisions, deals and people as they type.
 * Returns bar-ready result rows, only for the text currently in the box, so an
 * old answer never shows next to new typing.
 */
export default function useRecordSearch(text, { enabled = true } = {}) {
  const q = String(text || "").trim().toLowerCase().replace(/\s+/g, " ");
  const [state, setState] = useState({ q: "", items: [] });
  const [failed, setFailed] = useState(false);
  const active = enabled && q.length >= MIN_CHARS;

  useEffect(() => {
    if (!active) return undefined;
    let cancelled = false;
    const t = window.setTimeout(async () => {
      try {
        const res = await api.get("/search", { params: { q } });
        if (cancelled) return;
        const items = [];
        for (const g of res.data?.groups || []) {
          for (const it of g.items || []) {
            items.push({
              id: `rec-${g.kind}-${it.id}`,
              label: it.title,
              detail: it.detail,
              description: g.label.replace(/s$/, ""),
              to: it.to,
            });
          }
        }
        setFailed(false);
        setState({ q, items });
      } catch {
        if (!cancelled) {
          setFailed(true);
          setState({ q, items: [] });
        }
      }
    }, WAIT_MS);
    return () => { cancelled = true; window.clearTimeout(t); };
  }, [q, active]);

  const ready = active && state.q === q;
  return useMemo(() => ({
    items: ready ? state.items : [],
    searching: active && !ready && !failed,
  }), [ready, state.items, active, failed]);
}
