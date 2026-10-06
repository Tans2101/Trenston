import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Link, useNavigate } from "react-router-dom";
import { Send, CheckCircle2, Circle, AlertTriangle, Plus, Users, Lock, PenLine, Briefcase, Scale } from "lucide-react";
import CirDeleteBtn from "@/components/CirDeleteBtn";
import { useFetch, fetchErrorMessage } from "@/hooks/useFetch";
import { useDecisionActions, buildDelegateOptions, isOpenDecision } from "@/hooks/useDecisionActions";
import { useWorkspaceTimezone } from "@/hooks/useWorkspaceTimezone";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { todayISO } from "@/lib/dates";
import { dayPartGreeting } from "@/lib/greeting";
import {
  hasMyDaySoftRefreshError,
  isMyDayInitialLoading,
} from "@/lib/myDayUi";
import { GlassCard, SectionLabel, EmptyState, PageHeaderSkeleton, SkeletonCardList } from "@/components/kit";
import DecisionCard from "@/components/DecisionCard";
import SuggestionCard from "@/components/SuggestionCard";
import { departmentIcon } from "@/lib/departmentIcons";
import { taskHref } from "@/lib/signalRoute";
import { cn } from "@/lib/utils";

/* Sticky-note chips keep a distinct paper palette so notes stay scannable; not brand fills. */
const NOTE_STYLES = {
  gold: "bg-[#fef9c3] text-[#422006] border-[#eab308]/40 shadow-[3px_3px_0_rgba(234,179,8,0.35)]",
  sky: "bg-[#e0f2fe] text-[#0c4a6e] border-[#38bdf8]/40 shadow-[3px_3px_0_rgba(56,189,248,0.35)]",
  emerald: "bg-[#d1fae5] text-[#064e3b] border-[#34d399]/40 shadow-[3px_3px_0_rgba(52,211,153,0.35)]",
  rose: "bg-[#ffe4e6] text-[#881337] border-[#fb7185]/40 shadow-[3px_3px_0_rgba(251,113,133,0.35)]",
  violet: "bg-[#ede9fe] text-[#4c1d95] border-[#a78bfa]/40 shadow-[3px_3px_0_rgba(167,139,250,0.35)]",
  amber: "bg-[#fef3c7] text-[#78350f] border-[#fbbf24]/40 shadow-[3px_3px_0_rgba(251,191,36,0.35)]",
};

const colStyle = {
  done: "text-helm-status-positive",
  in_progress: "text-helm-gold",
  review: "text-helm-muted",
  backlog: "text-helm-muted",
};

const colLabel = { backlog: "To-Do", in_progress: "in progress", review: "review", done: "done" };

function SectionError({ label, error, onRetry }) {
  return (
    <GlassCard className="p-5" data-testid="myday-section-error">
      <p className="text-sm text-helm-fg">{label}</p>
      <p className="text-xs text-helm-muted mt-1">{fetchErrorMessage(error, "Could not load this section.")}</p>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 text-xs text-helm-gold hover:text-helm-gold-hover font-medium"
        >
          Retry
        </button>
      ) : null}
    </GlassCard>
  );
}

function SectionSkeleton({ count = 2 }) {
  return <SkeletonCardList count={count} />;
}

export default function MyDay() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const tz = useWorkspaceTimezone();
  const { data: notesData, loading: l0, error: e0, reload: reloadNotes } = useFetch("/notes");
  const { data: mine, loading: l1, error: e1, reload: reloadMine } = useFetch("/updates/me");
  const { data: tasks, loading: l2, error: e2, reload: reloadTasks } = useFetch("/tasks/me");
  const { data: today, loading: l3, error: e3, reload: reloadToday } = useFetch("/updates/today");
  const { data: decisionsData, loading: lDec, error: eDec, reload: reloadDecisions } = useFetch("/decisions");
  const canActDecisions = !!decisionsData?.can_act;
  const { data: membersData, loading: lMembers } = useFetch(canActDecisions ? "/members" : null);
  const { busy: decisionBusy, act, approveSuggestion, dismissSuggestion } = useDecisionActions(reloadDecisions);
  const { data: workData, loading: lWork, error: eWork, reload: reloadWork } = useFetch("/me/work-items");

  const [teamText, setTeamText] = useState("");
  const [blocker, setBlocker] = useState(false);
  const [busy, setBusy] = useState(false);
  const [showTeam, setShowTeam] = useState(false);
  const [showTask, setShowTask] = useState(false);
  const [taskTitle, setTaskTitle] = useState("");
  const [taskDue, setTaskDue] = useState("");
  const [taskBusy, setTaskBusy] = useState(false);
  const [taskMovingId, setTaskMovingId] = useState(null);
  const [editingNote, setEditingNote] = useState(null);
  const [noteText, setNoteText] = useState("");
  const [noteColor, setNoteColor] = useState("gold");
  const [noteBusy, setNoteBusy] = useState(false);
  const [showNoteComposer, setShowNoteComposer] = useState(false);

  const requiredFeeds = [
    { loading: l0, data: notesData, error: e0 },
    { loading: l1, data: mine, error: e1 },
    { loading: l2, data: tasks, error: e2 },
    { loading: l3, data: today, error: e3 },
    { loading: lWork, data: workData, error: eWork },
  ];
  const softRefreshError = hasMyDaySoftRefreshError(requiredFeeds);
  const softRefreshToastKey = useRef(null);

  const reloadAll = () => {
    reloadNotes();
    reloadMine();
    reloadTasks();
    reloadToday();
    reloadDecisions();
    reloadWork();
  };

  useEffect(() => {
    if (!softRefreshError) {
      softRefreshToastKey.current = null;
      return;
    }
    const err = e0 || e1 || e2 || e3 || eWork;
    const key = err?.message || err?.code || "soft-refresh";
    if (softRefreshToastKey.current === key) return;
    softRefreshToastKey.current = key;
    toast.error(fetchErrorMessage(err, "Could not refresh your day. Showing last loaded data."));
  }, [softRefreshError, e0, e1, e2, e3, eWork]);

  // Only full-page skeleton when every required feed is on first load (no cache).
  // Decisions never block the rest of My Day.
  if (isMyDayInitialLoading(requiredFeeds)) {
    return (
      <div>
        <PageHeaderSkeleton />
        <SkeletonCardList count={2} className="mb-6" />
        <div className="grid lg:grid-cols-2 gap-4">
          <SkeletonCardList count={3} />
          <SkeletonCardList count={3} />
        </div>
      </div>
    );
  }

  const first = user?.name?.split(" ")[0] || "there";
  const { greeting } = dayPartGreeting(new Date(), tz);
  const hasPosted = !!mine?.update;
  const notes = notesData?.notes || [];
  const suggestions = decisionsData?.suggestions || [];
  const { selfMember, delegateMembers, selfLabel, selfOptionLabel } = buildDelegateOptions(membersData);
  const pendingDecisions = (decisionsData?.decisions || []).filter((d) => isOpenDecision(d, selfLabel));
  const needsCallEmpty = suggestions.length === 0 && pendingDecisions.length === 0;
  const workItems = workData?.items || [];
  const membersReady = !canActDecisions || !!membersData;
  const delegateDisabled = canActDecisions && (lMembers || !membersReady);

  const saveNote = async () => {
    if (!noteText.trim()) { toast.error("Write something first"); return; }
    setNoteBusy(true);
    try {
      if (editingNote) {
        await api.patch(`/notes/${editingNote}`, { text: noteText.trim(), color: noteColor });
        toast.success("Note updated");
      } else {
        await api.post("/notes", { text: noteText.trim(), color: noteColor });
        toast.success("Private note saved");
      }
      setNoteText(""); setEditingNote(null); setShowNoteComposer(false);
      reloadNotes();
    } catch (e) { toast.error(e?.response?.data?.detail || "Could not save note"); }
    finally { setNoteBusy(false); }
  };

  const startEdit = (n) => {
    setEditingNote(n.note_id);
    setNoteText(n.text);
    setNoteColor(n.color || "gold");
    setShowNoteComposer(true);
  };

  const openNewNote = () => {
    setEditingNote(null);
    setNoteText("");
    setNoteColor("gold");
    setShowNoteComposer(true);
  };

  const cancelNote = () => {
    setEditingNote(null);
    setNoteText("");
    setShowNoteComposer(false);
  };

  const delNote = async (n) => {
    try { await api.delete(`/notes/${n.note_id}`); reloadNotes(); toast.success("Note deleted"); }
    catch (e) { toast.error("Could not delete"); }
  };

  const submitTeam = async () => {
    if (!teamText.trim()) { toast.error("Write a quick update first"); return; }
    setBusy(true);
    try {
      await api.post("/updates", { text: teamText.trim(), blocker });
      toast.success(hasPosted ? "Team update saved" : "Shared with your team");
      setTeamText(""); setShowTeam(false);
      reloadMine(); reloadToday();
    } catch (e) { toast.error(e?.response?.data?.detail || "Could not post"); }
    finally { setBusy(false); }
  };

  const addTask = async () => {
    if (!taskTitle.trim()) { toast.error("Add a title"); return; }
    setTaskBusy(true);
    try {
      await api.post("/tasks", { title: taskTitle.trim(), tag: "Personal", column: "backlog", due: taskDue });
      toast.success("Task added");
      setTaskTitle(""); setTaskDue(""); setShowTask(false);
      reloadTasks();
    } catch (e) { toast.error(e?.response?.data?.detail || "Could not add task"); }
    finally { setTaskBusy(false); }
  };

  const moveTask = async (t, column) => {
    if (taskMovingId) return;
    setTaskMovingId(t.id);
    try { await api.patch(`/tasks/${t.id}`, { column }); reloadTasks(); }
    catch (e) { toast.error("Could not update task"); }
    finally { setTaskMovingId(null); }
  };

  const myItems = tasks?.items || [];
  const openItems = myItems.filter((t) => t.column !== "done");
  const doneItems = myItems.filter((t) => t.column === "done");
  const teamUpdates = (today?.updates || []).filter((u) => u.user_id !== user?.user_id);
  const workspaceToday = todayISO(tz);

  // Turn a teammate's blocker into a decision, with the context already filled in.
  const logDecisionFromBlocker = (u) => {
    const text = (u.text || "").trim();
    const firstLine = text.split("\n")[0];
    const short = firstLine.length > 80 ? `${firstLine.slice(0, 77)}…` : firstLine;
    navigate("/app/decisions", {
      state: {
        openAdd: true,
        prefill: {
          title: short ? `Unblock ${u.user_name || "teammate"}: ${short}` : `Unblock ${u.user_name || "teammate"}`,
          description: text ? `${u.user_name || "A teammate"} reported a blocker: ${text}` : "",
          category: "Team",
        },
      },
    });
  };

  return (
    <div>
      <div className="mb-8 fade-up">
        <p className="font-mono text-xs uppercase tracking-[0.25em] text-helm-gold mb-3">My Day</p>
        <h1 className="font-display text-3xl md:text-5xl font-normal tracking-tight text-helm-fg">{greeting}, {first}.</h1>
        <p className="text-helm-muted mt-3 max-w-2xl text-base leading-relaxed">Your private notes, tasks, and optional team update. Start with what matters to you.</p>
      </div>

      {softRefreshError ? (
        <div
          className="mb-4 rounded-lg border border-helm-status-warning/40 bg-helm-status-warning/10 px-4 py-3 text-sm text-helm-fg"
          data-testid="myday-soft-refresh-error"
          role="status"
        >
          Could not refresh. Showing last loaded data.{" "}
          <button type="button" onClick={reloadAll} className="text-helm-gold hover:text-helm-gold-hover font-medium underline-offset-2 hover:underline">
            Retry
          </button>
        </div>
      ) : null}

      {/* Needs your call — never blocks the rest of the page */}
      {(lDec && !decisionsData) ? (
        <div className="mb-8 fade-up" data-testid="needs-your-call-loading">
          <SectionLabel>Needs your call</SectionLabel>
          <div className="mt-4"><SectionSkeleton count={2} /></div>
        </div>
      ) : eDec && !decisionsData ? (
        <div className="mb-8 fade-up" data-testid="needs-your-call">
          <SectionLabel>Needs your call</SectionLabel>
          <div className="mt-4">
            <SectionError label="Could not load decisions" error={eDec} onRetry={reloadDecisions} />
          </div>
        </div>
      ) : canActDecisions ? (
        <div className="mb-8 fade-up" data-testid="needs-your-call">
          <div className="flex items-center justify-between gap-3 mb-4">
            <SectionLabel>Needs your call</SectionLabel>
            <Link to="/app/decisions" className="text-xs text-helm-gold hover:text-helm-gold-hover font-medium shrink-0">
              See all decisions →
            </Link>
          </div>
          {eDec ? (
            <div
              className="mb-3 rounded-lg border border-helm-status-warning/40 bg-helm-status-warning/10 px-3 py-2 text-xs text-helm-fg"
              role="status"
            >
              Could not refresh decisions.{" "}
              <button type="button" onClick={reloadDecisions} className="text-helm-gold hover:text-helm-gold-hover font-medium">Retry</button>
            </div>
          ) : null}
          {needsCallEmpty ? (
            <GlassCard className="p-5">
              <p className="text-sm text-helm-fg">Nothing needs your call right now</p>
              <p className="text-xs text-helm-muted mt-1">You&apos;re all caught up. Open Decision Center anytime to log a new call or refresh suggestions.</p>
            </GlassCard>
          ) : (
            <div className="space-y-3">
              {suggestions.map((s) => (
                <SuggestionCard
                  key={s.id}
                  s={s}
                  canAct
                  busy={decisionBusy}
                  onAcceptSuggestion={approveSuggestion}
                  onDismissSuggestion={dismissSuggestion}
                />
              ))}
              {pendingDecisions.map((d) => (
                <DecisionCard
                  key={d.id}
                  d={d}
                  canAct
                  busy={decisionBusy || delegateDisabled}
                  onApprove={(id) => act(id, "approved")}
                  onReject={(id) => act(id, "rejected")}
                  onDelegate={(id, owner) => act(id, "delegated", owner)}
                  delegateMembers={delegateMembers}
                  selfMember={selfMember}
                  selfLabel={selfLabel}
                  selfOptionLabel={selfOptionLabel}
                />
              ))}
            </div>
          )}
        </div>
      ) : null}

      <div className="mb-8 fade-up" data-testid="my-work-feed">
        <div className="flex items-center gap-2 mb-4">
          <Briefcase className="w-3.5 h-3.5 text-helm-gold" />
          <SectionLabel>My Work</SectionLabel>
        </div>
        {lWork && !workData ? (
          <SectionSkeleton count={2} />
        ) : eWork && !workData ? (
          <SectionError label="Could not load My Work" error={eWork} onRetry={reloadWork} />
        ) : workItems.length === 0 ? (
          <GlassCard className="p-5">
            <p className="text-sm text-helm-fg">No department work assigned to you right now</p>
            <p className="text-xs text-helm-muted mt-1">Personal tasks are listed below. Department and deal work assigned to you shows up here.</p>
          </GlassCard>
        ) : (
          <div className="space-y-2">
            {workItems.map((item) => {
              const Icon = departmentIcon(item.icon);
              const dueLabel = item.due_date || "No due date";
              return (
                <Link
                  key={item.id}
                  to={item.url}
                  data-testid={`work-item-${item.id}`}
                  className="flex items-center gap-3 rounded-lg border border-helm-line bg-helm-card px-4 py-3 hover:border-helm-gold/40 transition-colors"
                >
                  <span className="shrink-0 text-helm-gold"><Icon className="w-4 h-4" /></span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-helm-fg truncate">{item.title}</p>
                    <p className="text-[11px] text-helm-muted mt-0.5">
                      {item.department_name || item.department_type}
                      {item.relationship === "requested_by_me" ? " · Requested by you" : ""}
                      {item.status ? ` · ${String(item.status).replace(/_/g, " ")}` : ""}
                    </p>
                  </div>
                  <div className="shrink-0 flex items-center gap-2">
                    {item.overdue && (
                      <span className="text-[10px] font-mono uppercase tracking-wider text-helm-status-negative bg-helm-status-negative/12 border border-helm-status-negative/35 rounded px-1.5 py-0.5">
                        Overdue
                      </span>
                    )}
                    <span className={cn("text-[11px] font-mono", item.overdue ? "text-helm-status-negative" : "text-helm-muted")}>
                      {dueLabel}
                    </span>
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </div>

      <div className="grid lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Lock className="w-3.5 h-3.5 text-helm-gold" />
              <SectionLabel>Notes</SectionLabel>
              <span className="text-[10px] font-mono uppercase tracking-wider text-helm-muted bg-helm-fg/5 rounded px-2 py-0.5">Private · only you</span>
            </div>
            <button
              data-testid="new-note-btn"
              type="button"
              onClick={openNewNote}
              className="inline-flex items-center gap-1 text-xs text-helm-gold hover:text-helm-gold-hover"
            >
              <Plus className="w-3.5 h-3.5" /> New note
            </button>
          </div>

          {showNoteComposer && (
            <GlassCard className="p-4 fade-up border-helm-gold/35" data-testid="note-composer">
              <textarea
                data-testid="note-text"
                value={noteText}
                onChange={(e) => setNoteText(e.target.value)}
                rows={3}
                placeholder="Jot a thought, reminder, or idea…"
                className="w-full rounded-lg border border-helm-line bg-helm-card text-helm-fg text-sm p-3 focus:outline-none focus:border-helm-gold/40 resize-none"
              />
              <div className="flex flex-wrap items-center gap-2 mt-3">
                {Object.keys(NOTE_STYLES).map((c) => (
                  <button key={c} type="button" onClick={() => setNoteColor(c)}
                    className={cn("w-6 h-6 rounded-full border-2", noteColor === c ? "border-helm-line scale-110" : "border-transparent opacity-70")}
                    style={{ background: c === "gold" ? "#eab308" : c === "sky" ? "#38bdf8" : c === "emerald" ? "#34d399" : c === "rose" ? "#fb7185" : c === "violet" ? "#a78bfa" : "#fbbf24" }}
                    aria-label={`${c} note color`}
                  />
                ))}
                <button data-testid="save-note-btn" onClick={saveNote} disabled={noteBusy}
                  className="ml-auto inline-flex items-center gap-1.5 rounded-md bg-helm-gold text-helm-navy text-sm font-medium px-3 py-1.5 hover:bg-helm-gold-hover disabled:opacity-60">
                  {noteBusy ? "Saving…" : editingNote ? "Save" : "Add note"}
                </button>
                <button type="button" data-testid="cancel-note-btn" onClick={cancelNote} className="text-xs text-helm-muted hover:text-helm-fg">Cancel</button>
              </div>
            </GlassCard>
          )}

          {l0 && !notesData ? (
            <SectionSkeleton count={2} />
          ) : e0 && !notesData ? (
            <SectionError label="Could not load notes" error={e0} onRetry={reloadNotes} />
          ) : notes.length === 0 && !showNoteComposer ? (
            <EmptyState title="No private notes yet" body="Sticky notes here are only visible to you, and are great for priorities, reminders, and scratch ideas."
              action={<button type="button" onClick={openNewNote} className="inline-flex items-center gap-1.5 rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-4 py-2 hover:bg-helm-gold-hover"><Plus className="w-4 h-4" /> Add your first note</button>} />
          ) : (
            <div className="grid sm:grid-cols-2 gap-3" data-testid="sticky-notes-grid">
              {notes.map((n) => (
                <div
                  key={n.note_id}
                  data-testid={`sticky-note-${n.note_id}`}
                  className={cn("relative rounded-sm border p-4 min-h-[120px] rotate-[-0.6deg] hover:rotate-0 transition-transform", NOTE_STYLES[n.color] || NOTE_STYLES.gold)}
                  style={{ fontFamily: "Georgia, 'Times New Roman', serif" }}
                >
                  <p className="text-sm leading-relaxed pr-6 whitespace-pre-wrap">{n.text}</p>
                  <div className="absolute top-2 right-2 flex gap-1">
                    <button onClick={() => startEdit(n)} className="opacity-60 hover:opacity-100 p-0.5"><PenLine className="w-3.5 h-3.5" /></button>
                    <CirDeleteBtn onClick={() => delNote(n)} data-testid={`del-note-${n.note_id}`} title="Delete note" />
                  </div>
                </div>
              ))}
            </div>
          )}

          <GlassCard className="p-4 fade-up">
            <button type="button" onClick={() => { setShowTeam((s) => !s); if (!showTeam && mine?.update) { setTeamText(mine.update.text || ""); setBlocker(!!mine.update.blocker); } }}
              className="flex items-center gap-2 text-sm text-helm-fg hover:text-helm-fg w-full text-left">
              <Users className="w-4 h-4 text-helm-gold" />
              <span>{showTeam ? "Hide team update" : "Share an update with your team (optional)"}</span>
            </button>
            {showTeam && (
              <div className="mt-3 pt-3 border-t border-helm-line" data-testid="team-update-form">
                {l1 && !mine ? (
                  <p className="text-xs text-helm-muted">Loading your update…</p>
                ) : e1 && !mine ? (
                  <p className="text-xs text-helm-muted">Could not load your update.{" "}
                    <button type="button" onClick={reloadMine} className="text-helm-gold">Retry</button>
                  </p>
                ) : (
                  <>
                    <textarea value={teamText} onChange={(e) => setTeamText(e.target.value)} rows={3}
                      placeholder="What did you move forward? Any blocker or ask?"
                      className="w-full rounded-lg border border-helm-line bg-helm-card text-helm-fg text-sm p-3 focus:outline-none focus:border-helm-gold/40 resize-none" />
                    <div className="flex flex-wrap items-center gap-3 mt-3">
                      <label className="flex items-center gap-2 text-sm text-helm-fg cursor-pointer">
                        <input type="checkbox" checked={blocker} onChange={(e) => setBlocker(e.target.checked)} className="accent-helm-gold w-4 h-4" />
                        <AlertTriangle className="w-3.5 h-3.5 text-helm-status-warning" /> Blocked
                      </label>
                      <button onClick={submitTeam} disabled={busy}
                        className="ml-auto inline-flex items-center gap-2 rounded-md bg-helm-gold text-helm-navy text-sm font-medium px-4 py-2 hover:bg-helm-gold-hover disabled:opacity-60">
                        {busy ? "Posting…" : "Post to team"} <Send className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </>
                )}
              </div>
            )}
          </GlassCard>
        </div>

        <GlassCard className="p-5 fade-up" data-testid="team-updates-card">
          <div className="flex items-center gap-1.5 mb-4 text-helm-gold"><Users className="w-3.5 h-3.5" /><SectionLabel>Today across the team</SectionLabel></div>
          {l3 && !today ? (
            <SectionSkeleton count={2} />
          ) : e3 && !today ? (
            <SectionError label="Could not load team updates" error={e3} onRetry={reloadToday} />
          ) : (
            <div className="space-y-3 max-h-[320px] overflow-y-auto">
              {mine?.update ? (
                <div className="text-sm pb-3 border-b border-helm-line" data-testid="my-team-update">
                  <div className="flex items-center gap-2">
                    <span className="text-helm-fg text-xs font-medium">You</span>
                    {mine.update.blocker && <span className="text-[10px] text-helm-fg bg-helm-status-warning/12 rounded px-1.5 py-0.5 font-mono uppercase">Blocked</span>}
                    <span className="text-[10px] text-helm-muted ml-auto font-mono">today</span>
                  </div>
                  <p className="text-helm-muted text-xs mt-1 leading-relaxed">{mine.update.text}</p>
                </div>
              ) : null}
              {teamUpdates.length === 0 && !mine?.update ? (
                <p className="text-sm text-helm-muted py-6 text-center">No teammate updates yet today.</p>
              ) : (
                teamUpdates.map((u) => (
                  <div key={u.update_id} className="text-sm" data-testid={`team-update-${u.update_id}`}>
                    <div className="flex items-center gap-2">
                      <span className="text-helm-fg text-xs font-medium">{u.user_name}</span>
                      {u.blocker && <span className="text-[10px] text-helm-fg bg-helm-status-warning/12 rounded px-1.5 py-0.5 font-mono uppercase">Blocked</span>}
                      <span className="text-[10px] text-helm-muted ml-auto font-mono">{u.ago}</span>
                    </div>
                    <p className="text-helm-muted text-xs mt-1 leading-relaxed">{u.text}</p>
                    {u.blocker && canActDecisions && (
                      <button
                        type="button"
                        data-testid={`log-decision-${u.update_id}`}
                        onClick={() => logDecisionFromBlocker(u)}
                        className="mt-1.5 inline-flex items-center gap-1 text-[11px] text-helm-gold hover:text-helm-gold-hover font-medium"
                      >
                        <Scale className="w-3 h-3" /> Log decision
                      </button>
                    )}
                  </div>
                ))
              )}
            </div>
          )}
        </GlassCard>
      </div>

      <div className="mt-6">
        <div className="flex items-center justify-between mb-4">
          <SectionLabel>My tasks</SectionLabel>
          <button data-testid="myday-add-task-btn" onClick={() => { setShowTask((s) => !s); if (!showTask && !taskDue) setTaskDue(workspaceToday); }}
            className="inline-flex items-center gap-1.5 rounded-md border border-helm-line text-helm-fg text-sm px-3 py-1.5 hover:bg-helm-fg/5">
            <Plus className="w-3.5 h-3.5" /> New task
          </button>
        </div>

        {showTask && (
          <GlassCard className="p-3 mb-3 fade-up">
            <div className="flex gap-2">
              <input data-testid="myday-task-input" value={taskTitle} onChange={(e) => setTaskTitle(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && addTask()} placeholder="What do you need to get done?"
                className="flex-1 rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40" />
              <input data-testid="myday-task-due" type="date" value={taskDue} min={workspaceToday} onChange={(e) => setTaskDue(e.target.value)}
                className="rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-2 py-2 focus:outline-none focus:border-helm-gold/40" />
              <button data-testid="myday-task-save" onClick={addTask} disabled={taskBusy}
                className="rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-4 py-2 hover:bg-helm-gold-hover disabled:opacity-60">{taskBusy ? "…" : "Add"}</button>
            </div>
          </GlassCard>
        )}

        {l2 && !tasks ? (
          <SectionSkeleton count={2} />
        ) : e2 && !tasks ? (
          <SectionError label="Could not load tasks" error={e2} onRetry={reloadTasks} />
        ) : myItems.length === 0 ? (
          <EmptyState icon={CheckCircle2} title="No tasks assigned to you" body="Add a personal task above, or your manager can assign work from the Tasks board." />
        ) : (
          <div className="space-y-2">
            {openItems.map((t) => {
              const overdue = t.due && /^\d{4}-\d{2}-\d{2}$/.test(t.due) && t.due < workspaceToday;
              return (
                <GlassCard key={t.id} className="p-3 fade-up flex items-center gap-3" data-testid={`myday-task-${t.id}`}>
                  <button
                    type="button"
                    disabled={taskMovingId === t.id}
                    onClick={() => moveTask(t, "done")}
                    className="text-helm-muted hover:text-helm-status-positive shrink-0 disabled:opacity-50"
                  >
                    <Circle className="w-4 h-4" />
                  </button>
                  <Link to={taskHref(t.id)} className="flex-1 min-w-0 group" data-testid={`myday-task-link-${t.id}`}>
                    <p className="text-sm text-helm-fg truncate group-hover:text-helm-gold transition-colors">{t.title}</p>
                    <span className={cn("text-[10px] font-mono uppercase tracking-wide", colStyle[t.column])}>
                      {colLabel[t.column] || String(t.column || "").replace("_", " ")}{t.tag ? ` · ${t.tag}` : ""}
                    </span>
                  </Link>
                  {t.due && (
                    <span className={cn("text-[11px] font-mono shrink-0", overdue ? "text-helm-status-negative" : "text-helm-muted")}>
                      {t.due}
                    </span>
                  )}
                </GlassCard>
              );
            })}
            {doneItems.map((t) => (
              <GlassCard key={t.id} className="p-3 flex items-center gap-3 opacity-60" data-testid={`myday-task-${t.id}`}>
                <button
                  type="button"
                  disabled={taskMovingId === t.id}
                  onClick={() => moveTask(t, "in_progress")}
                  className="text-helm-status-positive shrink-0 disabled:opacity-50"
                >
                  <CheckCircle2 className="w-4 h-4" />
                </button>
                <Link to={taskHref(t.id)} className="text-sm text-helm-muted line-through truncate flex-1 hover:text-helm-fg transition-colors">{t.title}</Link>
              </GlassCard>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
