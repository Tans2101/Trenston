import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { AlertTriangle, CornerDownLeft } from "lucide-react";
import { api, apiErrorMessage } from "@/lib/api";
import { KIND_LABEL, parseCommand, prettyDate, requestFor } from "@/lib/commandBar";
import { cn } from "@/lib/utils";

function Row({ label, children }) {
  return (
    <div className="flex items-baseline gap-3 text-sm">
      <span className="w-16 shrink-0 text-[10px] font-mono uppercase tracking-wider text-helm-muted">{label}</span>
      <span className="min-w-0 flex-1 text-helm-fg">{children}</span>
    </div>
  );
}

export function QuickAddPanel({ parsed, loadingTeam, saving, onPick }) {
  const { kind } = parsed;
  return (
    <div className="p-4 space-y-3" data-testid="quick-add-panel">
      <p className="text-xs font-medium text-helm-gold">{KIND_LABEL[kind]}</p>
      <div className="space-y-1.5">
        <Row label={kind === "note" ? "Note" : "Title"}>
          {parsed.title || <span className="text-helm-muted">Nothing yet</span>}
        </Row>
        {kind !== "note" && (
          <Row label="Due">
            {parsed.due ? prettyDate(parsed.due) : <span className="text-helm-muted">No date</span>}
          </Row>
        )}
        {kind === "task" && (
          <>
            <Row label="Who">
              {parsed.assignee
                ? (parsed.assignee.self ? "You" : parsed.assignee.name)
                : <span className="text-helm-muted">You</span>}
            </Row>
            <Row label="Priority">{parsed.priority || <span className="text-helm-muted">Medium</span>}</Row>
            {parsed.tag ? <Row label="Tag">{parsed.tag}</Row> : null}
          </>
        )}
        {kind === "decision" && (
          <Row label="Impact">{parsed.priority || <span className="text-helm-muted">Medium</span>}</Row>
        )}
      </div>

      {parsed.ambiguous && (
        <div className="rounded-md border border-helm-gold/30 bg-helm-gold/10 p-2.5 text-sm" data-testid="quick-add-ambiguous">
          <p className="text-helm-fg">Which &ldquo;{parsed.ambiguous.word}&rdquo;?</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {parsed.ambiguous.options.map((o) => (
              <button
                key={o.user_id}
                type="button"
                onClick={() => onPick(o.user_id)}
                className="rounded-full border border-helm-line bg-helm-card px-3 py-1 text-sm text-helm-fg hover:border-helm-gold/50"
              >
                {o.name}
              </button>
            ))}
          </div>
          <p className="mt-2 text-xs text-helm-muted">Or type their full name.</p>
        </div>
      )}

      {parsed.issues.map((msg) => (
        <p key={msg} className="flex items-start gap-1.5 text-sm text-helm-gold" data-testid="quick-add-issue">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" /> {msg}
        </p>
      ))}

      <p className={cn("flex items-center gap-1.5 text-xs", parsed.ready && !loadingTeam ? "text-helm-fg" : "text-helm-muted")}>
        <CornerDownLeft className="h-3.5 w-3.5" />
        {saving ? "Saving…" : loadingTeam ? "Loading your team…" : parsed.ready ? "Press Enter to save" : "Fix the above, then press Enter"}
      </p>
    </div>
  );
}

/**
 * Quick add for the ⌘K bar: parses what is typed, shows what was understood, and only
 * saves on Enter, through the same endpoints (and permission checks) as the pages.
 */
export function useQuickAdd({ me, onDone }) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [members, setMembers] = useState(null);
  const [pick, setPick] = useState("");
  const [saving, setSaving] = useState(false);
  const fetching = useRef(false);

  const isTaskLike = /^\s*(?:add\s+(?:a\s+)?task|new\s+task|task|to-?do|todo|remind\s+me\s+to|reminder)\b/i.test(query);
  useEffect(() => {
    if (!isTaskLike || members !== null || fetching.current) return;
    fetching.current = true;
    api.get("/members")
      .then((res) => setMembers(res.data?.members || []))
      .catch(() => setMembers([]))
      .finally(() => { fetching.current = false; });
  }, [isTaskLike, members]);

  const parsed = useMemo(
    () => parseCommand(query, { members: members || [], myUserId: me, assigneeId: pick }),
    [query, members, me, pick],
  );
  const loadingTeam = Boolean(parsed && parsed.kind === "task" && members === null);

  const save = useCallback(async () => {
    if (!parsed || !parsed.ready || loadingTeam || saving) return;
    const req = requestFor(parsed, { myUserId: me });
    setSaving(true);
    try {
      await api.post(req.path, req.body);
      toast.success(req.done, { action: { label: "View", onClick: () => navigate(req.view) } });
      onDone?.();
    } catch (e) {
      toast.error(apiErrorMessage(e, "Could not save that"));
    } finally {
      setSaving(false);
    }
  }, [parsed, loadingTeam, saving, me, navigate, onDone]);

  const panel = parsed
    ? <QuickAddPanel parsed={parsed} loadingTeam={loadingTeam} saving={saving} onPick={setPick} />
    : null;

  return { onQueryChange: setQuery, panel, onEnter: save };
}
