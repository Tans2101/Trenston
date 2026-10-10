import { useState, useEffect, useRef, useMemo, Fragment } from "react";
import {
  ArrowUp, Square, ArrowUpRight, Copy, RotateCcw, Scale, ListTodo, SquarePen, Database,
} from "lucide-react";
import { toast } from "sonner";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { useFetch, useInvalidateFetch } from "@/hooks/useFetch";
import { useAuth } from "@/context/AuthContext";
import { useCompanyQuery } from "@/hooks/useCompanyQuery";
import { API, api, getApiAuthHeaders, apiErrorMessage, apiForbiddenReason } from "@/lib/api";
import { cn } from "@/lib/utils";
import { dayPartGreeting } from "@/lib/greeting";
import { parseAskBlocks, parseAskInline, askPlainText, askTaskTitle } from "@/lib/askText";
import AITextLoading from "@/components/kokonutui/ai-text-loading";
import TrenstonMark from "@/components/HelmMark";

const BASE_SUGGESTIONS = [
  "What's the single most important thing today?",
  "How many months of runway do we really have?",
  "Which decision should I make first and why?",
  "Where is my team over capacity?",
];

const FINANCE_SUGGESTION_RE = /\b(runway|mrr|burn|cash|revenue|financial)\b/i;

const ENGINE_ERROR = "I couldn't reach my reasoning engine. Please try again.";
const EMPTY_ANSWER = "No answer came back. Try again.";
const STOPPED_NOTE = "\n\n_(Stopped.)_";
const MAX_INPUT_HEIGHT = 200;
// Follow the stream only while the reader is this close to the bottom.
const STICKY_BOTTOM_PX = 120;

/** Replace the pending (last) assistant message, keeping its metadata. */
const patchLast = (patch) => (m) => {
  const copy = [...m];
  copy[copy.length - 1] = { ...copy[copy.length - 1], role: "assistant", ...patch };
  return copy;
};

function dayKey(iso) {
  const d = iso ? new Date(iso) : new Date();
  return Number.isNaN(d.getTime()) ? "" : d.toDateString();
}

function dayLabel(key) {
  if (!key) return "";
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(today.getDate() - 1);
  if (key === today.toDateString()) return "Today";
  if (key === yesterday.toDateString()) return "Yesterday";
  return new Date(key).toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
}

function agoLabel(iso) {
  if (!iso) return "";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "";
  const mins = Math.max(0, Math.round((Date.now() - t) / 60000));
  if (mins < 2) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.round(hrs / 24);
  return `${days}d ago`;
}

function InlineRuns({ text }) {
  return parseAskInline(text).map((r, i) => {
    if (r.bold) return <strong key={i} className="font-semibold text-helm-fg">{r.text}</strong>;
    if (r.italic) return <em key={i} className="text-helm-muted">{r.text}</em>;
    if (r.code) return <code key={i} className="rounded bg-helm-fg/10 px-1 py-0.5 font-mono text-[0.85em]">{r.text}</code>;
    return <Fragment key={i}>{r.text}</Fragment>;
  });
}

function AnswerBody({ text }) {
  return (
    <div className="space-y-3">
      {parseAskBlocks(text).map((b, i) => {
        if (b.type === "h") {
          return <p key={i} className="font-semibold text-helm-fg"><InlineRuns text={b.text} /></p>;
        }
        if (b.type === "ul" || b.type === "ol") {
          const List = b.type === "ul" ? "ul" : "ol";
          return (
            <List key={i} className={cn("space-y-1.5 pl-5", b.type === "ul" ? "list-disc" : "list-decimal", "marker:text-helm-muted")}>
              {b.items.map((it, j) => <li key={j} className="pl-1"><InlineRuns text={it} /></li>)}
            </List>
          );
        }
        return (
          <p key={i}>
            {b.lines.map((line, j) => (
              <Fragment key={j}>{j > 0 && <br />}<InlineRuns text={line} /></Fragment>
            ))}
          </p>
        );
      })}
    </div>
  );
}

function ActionButton({ icon: Icon, label, onClick, testId }) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={testId}
      className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-xs text-helm-muted transition-colors hover:bg-helm-fg/5 hover:text-helm-fg"
    >
      <Icon className="h-3.5 w-3.5" /> {label}
    </button>
  );
}

const toMessage = (m) => ({
  role: m.role,
  content: m.content,
  isError: Boolean(m.is_error),
  basis: m.basis || null,
  dataAsOf: m.data_as_of || null,
  createdAt: m.created_at || null,
});

export default function AskHelm() {
  const { user } = useAuth();
  const { data: company } = useCompanyQuery();
  const { data: history } = useFetch("/ask/history");
  const { data: billing, reload: reloadBilling } = useFetch("/billing/plans");
  const canSeeFinancials = (user?.granted_sections || []).includes("financials");
  const { data: fin } = useFetch(canSeeFinancials ? "/financials" : null);
  const invalidateFetch = useInvalidateFetch();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [resetting, setResetting] = useState(false);
  const scrollRef = useRef(null);
  const inputRef = useRef(null);
  const stickToBottom = useRef(true);
  const abortRef = useRef(null);
  const autoSent = useRef(false);
  // True once the user sends (or starts a new chat) in this visit; from then on local state owns the thread.
  const sentThisVisit = useRef(false);
  const navigate = useNavigate();
  const location = useLocation();
  const firstName = (user?.name || company?.ceo_name || "there").split(" ")[0];
  const { greeting: timeGreet } = dayPartGreeting();

  // Live-data prompts first (low runway, falling MRR), then the standing ones.
  const suggestions = useMemo(() => {
    const live = [];
    const runway = fin?.runway_months != null ? Number(fin.runway_months) : null;
    if (runway != null && Number.isFinite(runway) && runway < 12 && fin?.cash_state !== "zero_confirmed") {
      live.push(`Runway is ${runway} months. What are the fastest ways to extend it?`);
    }
    if (fin?.mrr_known && Number(fin?.mrr_delta) < 0) {
      live.push(`Why did MRR drop ${Math.abs(fin.mrr_delta)}% this month?`);
    }
    const base = BASE_SUGGESTIONS.filter((s) => canSeeFinancials || !FINANCE_SUGGESTION_RE.test(s));
    const filtered = live.length ? base.filter((s) => !/runway/i.test(s) || !live.some((l) => /runway/i.test(l))) : base;
    return [...live, ...filtered].slice(0, 4);
  }, [fin, canSeeFinancials]);

  const askLimit = Number(billing?.ask_helm_limit) || 0;
  const askUsed = Number(billing?.ask_helm_used) || 0;
  const showQuota = Boolean(billing?.billing_enforced) && askLimit > 0;
  const askLeft = Math.max(askLimit - askUsed, 0);
  const outOfMessages = showQuota && askLeft === 0;
  const resetLabel = billing?.usage_period_end
    ? new Date(billing.usage_period_end).toLocaleDateString(undefined, { month: "short", day: "numeric" })
    : "";

  useEffect(() => {
    // Mirror server history until the user acts in this visit. The cache can hand
    // us a stale copy first and the fresh one a moment later, so keep applying
    // updates rather than locking in whichever arrived first.
    if (sentThisVisit.current || streaming) return;
    if (!history?.messages) return;
    setMessages(history.messages.map(toMessage));
  }, [history, streaming]);

  useEffect(() => {
    const el = scrollRef.current;
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight;
  }, [messages]);

  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < STICKY_BOTTOM_PX;
  };

  const resizeInput = () => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_INPUT_HEIGHT)}px`;
  };

  useEffect(resizeInput, [input]);

  const send = async (text) => {
    const q = (text ?? input).trim();
    if (!q || streaming) return;
    sentThisVisit.current = true;
    stickToBottom.current = true;
    setInput("");
    const now = new Date().toISOString();
    setMessages((m) => [...m, { role: "user", content: q, createdAt: now }, { role: "assistant", content: "", createdAt: now }]);
    setStreaming(true);
    const controller = new AbortController();
    abortRef.current = controller;
    let acc = "";
    try {
      const headers = await getApiAuthHeaders({ "Content-Type": "application/json" });
      const res = await fetch(`${API}/ask`, {
        method: "POST",
        headers,
        credentials: "include",
        body: JSON.stringify({ message: q }),
        signal: controller.signal,
      });
      if (res.status === 403) {
        let body = null;
        try {
          body = await res.json();
        } catch {
          body = null;
        }
        const reason = apiForbiddenReason(body) || "plan";
        const message = apiErrorMessage(
          body,
          reason === "permission"
            ? "You don't have access to Ask Trenston. Ask a workspace owner if you need it."
            : "Ask Trenston isn't included in your plan",
        );
        if (reason === "permission") {
          setMessages(patchLast({ content: message, isError: true }));
          return;
        }
        setMessages((m) => m.slice(0, -2));
        navigate("/app/billing", { state: { billingNotice: message } });
        return;
      }
      if (res.status === 429) {
        let detail = "You've used your Ask Trenston messages this month. Upgrade to continue.";
        try {
          const body = await res.json();
          if (body?.detail) detail = apiErrorMessage(body, detail);
        } catch {
          /* keep default */
        }
        setMessages(patchLast({
          content: detail,
          isError: true,
          noRetry: true,
          link: { to: "/app/billing", label: "Open Billing to upgrade" },
        }));
        return;
      }
      if (!res.ok || !res.body) {
        setMessages(patchLast({ content: ENGINE_ERROR, isError: true }));
        return;
      }
      const basisHeader = res.headers.get("X-Ask-Basis");
      const meta = {
        basis: basisHeader ? basisHeader.split(",").filter(Boolean) : null,
        dataAsOf: res.headers.get("X-Ask-Data-As-Of") || null,
      };
      setMessages(patchLast(meta));
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        acc += decoder.decode(value, { stream: true });
        setMessages(patchLast({ content: acc }));
      }
      const tail = decoder.decode();
      if (tail) {
        acc += tail;
        setMessages(patchLast({ content: acc }));
      }
      // An empty stream would otherwise leave the loading indicator up forever.
      if (!acc.trim()) setMessages(patchLast({ content: EMPTY_ANSWER, isError: true }));
    } catch (e) {
      if (e?.name === "AbortError") {
        setMessages(patchLast(acc.trim() ? { content: acc + STOPPED_NOTE, stopped: true } : { content: "Stopped before an answer came back.", isError: true }));
      } else {
        setMessages(patchLast({ content: ENGINE_ERROR, isError: true }));
      }
    } finally {
      abortRef.current = null;
      setStreaming(false);
      // POST /ask goes through fetch, not the api client, so drop the cached
      // history here; coming back to this page then shows the latest exchange.
      invalidateFetch("/ask/history");
      reloadBilling();
      inputRef.current?.focus();
    }
  };

  const stop = () => abortRef.current?.abort();

  const newChat = async () => {
    if (streaming || resetting) return;
    setResetting(true);
    try {
      await api.post("/ask/new");
      sentThisVisit.current = true;
      setMessages([]);
      invalidateFetch("/ask/history");
      inputRef.current?.focus();
    } catch {
      toast.error("Could not start a new chat. Try again.");
    } finally {
      setResetting(false);
    }
  };

  /** Re-ask the question behind the answer at index i (drops a failed pair first). */
  const retry = (i) => {
    const question = [...messages.slice(0, i)].reverse().find((m) => m.role === "user")?.content;
    if (!question) return;
    if (messages[i]?.isError) setMessages((m) => m.filter((_, j) => j !== i && j !== i - 1));
    send(question);
  };

  const copyAnswer = async (text) => {
    try {
      await navigator.clipboard.writeText(askPlainText(text));
      toast.success("Copied");
    } catch {
      toast.error("Could not copy");
    }
  };

  const questionBefore = (i) => [...messages.slice(0, i)].reverse().find((m) => m.role === "user")?.content || "";

  const logDecision = (i) => {
    const question = questionBefore(i);
    navigate("/app/decisions", {
      state: {
        openAdd: true,
        prefill: {
          title: (question || askTaskTitle(messages[i].content)).slice(0, 140),
          description: askPlainText(messages[i].content).slice(0, 2000),
        },
      },
    });
  };

  const createTask = (i) => {
    navigate("/app/tasks", { state: { prefillTask: { title: askTaskTitle(messages[i].content) } } });
  };

  // Prefill from Briefing assistant chips (or similar navigators).
  useEffect(() => {
    const prefill = location.state?.prefill;
    if (!prefill || autoSent.current) return undefined;
    autoSent.current = true;
    const shouldSend = Boolean(location.state?.autoSend);
    navigate(location.pathname, { replace: true, state: {} });
    if (shouldSend) {
      const t = window.setTimeout(() => send(prefill), 0);
      return () => window.clearTimeout(t);
    }
    setInput(prefill);
    return undefined;
    // Intentionally once on mount/navigation with state — send is stable enough for this kickoff.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.state]);

  const empty = messages.length === 0;
  const lastIndex = messages.length - 1;
  const showFollowUps = !empty && !streaming && !input && messages[lastIndex]?.role === "assistant" && !messages[lastIndex]?.isError;

  return (
    <div className="mx-auto flex h-[calc(100dvh-7.5rem)] w-full max-w-4xl flex-col md:h-[calc(100dvh-8.5rem)]" data-testid="ask-trenston-layout">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="font-display text-3xl font-normal tracking-tight text-helm-fg md:text-4xl">Ask Trenston</h1>
          <p className="mt-2 text-sm text-helm-muted">Answers grounded in your live company data.</p>
        </div>
        {!empty && (
          <button
            type="button"
            data-testid="ask-new-chat-btn"
            onClick={newChat}
            disabled={streaming || resetting}
            className="mt-1 inline-flex shrink-0 items-center gap-1.5 rounded-md border border-helm-line px-3 py-2 text-sm text-helm-fg transition-colors hover:bg-helm-fg/5 disabled:opacity-50"
          >
            <SquarePen className="h-4 w-4" /> New chat
          </button>
        )}
      </div>

      <div ref={scrollRef} onScroll={onScroll} className="min-h-0 flex-1 overflow-y-auto overscroll-contain" data-testid="ask-thread">
        {empty && (
          <div className="pt-6">
            <TrenstonMark size={40} />
            <h2 className="mt-5 font-display text-2xl leading-tight tracking-tight text-helm-fg md:text-3xl">
              {timeGreet === "Hello"
                ? `What's on your plate today, ${firstName}?`
                : `${timeGreet}, ${firstName}. What's on your plate?`}
            </h2>
            <p className="mt-2 text-sm text-helm-muted">
              Ask about cash, runway, decisions, deals or your team. Answers only use data you can see in Trenston.
            </p>
            <div className="mt-8 grid grid-cols-1 gap-2 sm:grid-cols-2">
              {suggestions.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => send(s)}
                  data-testid="ask-suggestion"
                  className="rounded-lg border border-helm-line bg-helm-fg/[0.02] p-3.5 text-left text-sm text-helm-fg transition-colors hover:border-helm-gold/35 hover:bg-helm-fg/[0.04]"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="space-y-8 pb-6 pr-3">
          {messages.map((m, i) => {
            const key = dayKey(m.createdAt);
            const prevKey = i > 0 ? dayKey(messages[i - 1].createdAt) : null;
            const divider = m.createdAt && key !== prevKey ? (
              <div className="flex items-center gap-3 pt-2" aria-hidden>
                <span className="h-px flex-1 bg-helm-line" />
                <span className="font-mono text-[10px] uppercase tracking-wider text-helm-muted">{dayLabel(key)}</span>
                <span className="h-px flex-1 bg-helm-line" />
              </div>
            ) : null;

            if (m.role === "user") {
              return (
                <Fragment key={i}>
                  {divider}
                  <div className="flex justify-end" data-testid="msg-user">
                    <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md border border-helm-line bg-helm-fg/10 px-4 py-2.5 text-[15px] leading-relaxed text-helm-fg">
                      {m.content}
                    </div>
                  </div>
                </Fragment>
              );
            }

            const pending = !m.content;
            const isLive = streaming && i === lastIndex;
            return (
              <Fragment key={i}>
                {divider}
                <div className="group flex items-start gap-3" data-testid={m.isError ? "msg-error" : "msg-assistant"}>
                  <TrenstonMark size={24} className="mt-0.5 shrink-0" />
                  <div className="min-w-0 flex-1">
                    {pending ? (
                      <AITextLoading />
                    ) : m.isError ? (
                      <div className="rounded-lg border border-helm-status-negative/25 bg-helm-status-negative/5 px-4 py-3 text-sm text-helm-fg">
                        <p>{m.content}</p>
                        <div className="mt-2 flex flex-wrap items-center gap-3">
                          {m.link && (
                            <Link
                              to={m.link.to}
                              data-testid="ask-message-link"
                              className="inline-flex items-center gap-1 text-sm font-medium text-helm-gold hover:text-helm-gold-hover"
                            >
                              {m.link.label} <ArrowUpRight className="h-3.5 w-3.5" />
                            </Link>
                          )}
                          {!m.noRetry && !streaming && (
                            <button
                              type="button"
                              data-testid="ask-retry-btn"
                              onClick={() => retry(i)}
                              className="inline-flex items-center gap-1 text-sm text-helm-muted hover:text-helm-fg"
                            >
                              <RotateCcw className="h-3.5 w-3.5" /> Try again
                            </button>
                          )}
                        </div>
                      </div>
                    ) : (
                      <>
                        <div className="text-[15px] leading-relaxed text-helm-fg">
                          <AnswerBody text={m.content} />
                        </div>
                        {!isLive && (
                          <div className={`mt-2 flex flex-wrap items-center gap-x-1 gap-y-1 transition-opacity ${i === lastIndex ? "" : "opacity-0 focus-within:opacity-100 group-hover:opacity-100"}`}>
                            <ActionButton icon={Copy} label="Copy" onClick={() => copyAnswer(m.content)} testId="ask-copy-btn" />
                            <ActionButton icon={Scale} label="Log as decision" onClick={() => logDecision(i)} testId="ask-log-decision-btn" />
                            <ActionButton icon={ListTodo} label="Create task" onClick={() => createTask(i)} testId="ask-create-task-btn" />
                            {i === lastIndex && (
                              <ActionButton icon={RotateCcw} label="Retry" onClick={() => retry(i)} testId="ask-regenerate-btn" />
                            )}
                          </div>
                        )}
                        {!isLive && m.basis?.length > 0 && (
                          <p className="mt-2 flex items-start gap-1.5 text-[11px] leading-relaxed text-helm-muted" data-testid="ask-basis">
                            <Database className="mt-0.5 h-3 w-3 shrink-0" />
                            <span>
                              Based on {m.basis.join(", ")}
                              {m.dataAsOf ? ` · data as of ${agoLabel(m.dataAsOf)}` : ""}
                            </span>
                          </p>
                        )}
                      </>
                    )}
                  </div>
                </div>
              </Fragment>
            );
          })}
        </div>
      </div>

      <div className="border-t border-helm-line pt-3">
        {showFollowUps && suggestions.length > 0 && (
          <div className="mb-3 flex flex-wrap gap-2" data-testid="ask-followups">
            {suggestions.slice(0, 2).map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => send(s)}
                className="max-w-full truncate rounded-full border border-helm-line px-3 py-1.5 text-xs text-helm-muted transition-colors hover:border-helm-gold/35 hover:text-helm-fg"
              >
                {s}
              </button>
            ))}
          </div>
        )}
        <div className="flex items-end gap-2 rounded-xl border border-helm-line bg-helm-card px-2 py-2 transition-colors focus-within:border-helm-gold/35">
          <textarea
            ref={inputRef}
            data-testid="ask-input"
            rows={1}
            value={input}
            disabled={outOfMessages}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                send();
              }
            }}
            placeholder={outOfMessages ? "You've used this period's messages." : "Ask Trenston anything about your company…"}
            className="max-h-[200px] flex-1 resize-none bg-transparent px-2 py-1.5 text-sm leading-relaxed text-helm-fg placeholder:text-helm-muted focus:outline-none disabled:opacity-60"
          />
          {streaming ? (
            <button
              data-testid="ask-stop-btn"
              type="button"
              onClick={stop}
              aria-label="Stop answer"
              title="Stop"
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-helm-line text-helm-fg transition-colors hover:bg-helm-fg/5"
            >
              <Square className="h-3.5 w-3.5 fill-current" />
            </button>
          ) : (
            <button
              data-testid="ask-send-btn"
              type="button"
              onClick={() => send()}
              disabled={!input.trim() || outOfMessages}
              aria-label="Send"
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-helm-gold text-helm-navy transition-colors hover:bg-helm-gold-hover disabled:opacity-40"
            >
              <ArrowUp className="h-4 w-4" />
            </button>
          )}
        </div>
        <div className="mt-2 flex flex-wrap items-center justify-between gap-x-4 gap-y-1 text-[11px] text-helm-muted">
          <span><span className="hidden sm:inline">Enter to send, Shift + Enter for a new line. </span>Trenston can make mistakes, so check important numbers.</span>
          {showQuota && (
            <span data-testid="ask-quota" className={cn(askLeft <= 2 && "text-helm-status-warning")}>
              {askLeft} of {askLimit} left{resetLabel ? `, resets ${resetLabel}` : ""}
              {askLeft <= 2 && (
                <> · <Link to="/app/billing" className="underline hover:text-helm-fg">Upgrade</Link></>
              )}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
