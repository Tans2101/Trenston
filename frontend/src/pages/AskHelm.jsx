import { useState, useEffect, useRef } from "react";
import {
  Send, Sparkles, User, Plus, Share2, Download, ChevronDown,
  Building2, UsersRound, FileText, Link2, GitBranch, KanbanSquare, Wallet,
} from "lucide-react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { useFetch } from "@/hooks/useFetch";
import { useAuth } from "@/context/AuthContext";
import { useCompanyQuery } from "@/hooks/useCompanyQuery";
import { API, getApiAuthHeaders, apiErrorMessage, apiForbiddenReason } from "@/lib/api";
import { cn } from "@/lib/utils";
import { dayPartGreeting } from "@/lib/greeting";
import AITextLoading from "@/components/kokonutui/ai-text-loading";

const SUGGESTIONS = [
  "What's the single most important thing today?",
  "How many months of runway do we really have?",
  "Which decision should I make first and why?",
  "Where is my team over capacity?",
];

const FINANCE_SUGGESTION_RE = /\b(runway|mrr|burn|cash|revenue|financial)\b/i;

const GET_STARTED = [
  { label: "Connect your bank", to: "/app/integrations", icon: Link2, bg: "bg-helm-navy" },
  { label: "Invite your team", to: "/app/members", icon: UsersRound, bg: "bg-helm-gold" },
  { label: "Set up your first report", to: "/app/reports", icon: FileText, bg: "bg-helm-ink-card" },
];

export default function AskHelm() {
  const { user } = useAuth();
  const { data: company } = useCompanyQuery();
  const { data: history } = useFetch("/ask/history");
  const { data: briefing } = useFetch("/briefing");
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const scrollRef = useRef(null);
  const autoSent = useRef(false);
  const historyHydrated = useRef(false);
  const navigate = useNavigate();  const location = useLocation();
  const canSeeFinancials = (user?.granted_sections || []).includes("financials");
  const suggestions = SUGGESTIONS.filter(
    (s) => canSeeFinancials || !FINANCE_SUGGESTION_RE.test(s),
  );
  const firstName = (user?.name || company?.ceo_name || "there").split(" ")[0];
  const { greeting: timeGreet } = dayPartGreeting();
  const companyName = company?.name || "your company";

  const forYouCards = (() => {
    const cards = [];
    const decide = (briefing?.what_to_decide || []).slice(0, 2);
    decide.forEach((d) => {
      cards.push({
        title: d.title || d.label || "Open decision",
        caption: "Decisions",
        to: "/app/decisions",
        icon: GitBranch,
        tone: "bg-helm-gold/12 text-helm-gold",
      });
    });
    const changed = (briefing?.what_changed || []).slice(0, 2);
    changed.forEach((c) => {
      if (cards.length >= 3) return;
      cards.push({
        title: c.title || c.label || c.text || "Company update",
        caption: "Briefing",
        to: "/app",
        icon: Building2,
        tone: "bg-helm-navy/10 text-helm-navy",
      });
    });
    while (cards.length < 3) {
      const fillers = [
        { title: "Review open tasks", caption: "Tasks", to: "/app/tasks", icon: KanbanSquare, tone: "bg-helm-status-warning/12 text-helm-status-warning" },
        { title: "Check runway", caption: "Financials", to: "/app/financials", icon: Wallet, tone: "bg-helm-status-positive/12 text-helm-status-positive" },
        { title: "Scan today’s briefing", caption: "Briefing", to: "/app", icon: Building2, tone: "bg-helm-gold/12 text-helm-gold" },
      ];
      cards.push(fillers[cards.length]);
    }
    return cards.slice(0, 3);
  })();

  const inspiredCards = (() => {
    const cards = [];
    if (briefing?.ai_summary) {
      cards.push({
        title: "Today’s AI briefing",
        caption: "Generated summary",
        to: "/app",
        author: "Trenston",
      });
    }
    (briefing?.what_to_decide || []).slice(0, 2).forEach((d) => {
      cards.push({
        title: d.title || "Decision write-up",
        caption: d.rationale || d.reason || "Needs a call",
        to: "/app/decisions",
        author: "Decision Center",
      });
    });
    while (cards.length < 3) {
      cards.push({
        title: cards.length === 0 ? "Ask about runway" : cards.length === 1 ? "Prioritize decisions" : "Team capacity check",
        caption: "Try in Ask Trenston",
        to: null,
        author: "Suggested",
        prompt: SUGGESTIONS[cards.length % SUGGESTIONS.length],
      });
    }
    return cards.slice(0, 3);
  })();

  useEffect(() => {
    // Apply server history once. Never overwrite an in-flight or already-started chat
    // when /ask/history resolves after the user has already sent a message.
    if (historyHydrated.current || streaming) return;
    if (!history?.messages) return;
    historyHydrated.current = true;
    setMessages((prev) => {
      if (prev.length > 0) return prev;
      return history.messages.map((m) => ({ role: m.role, content: m.content }));
    });
  }, [history, streaming]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, streaming]);

  const send = async (text) => {
    const q = (text ?? input).trim();
    if (!q || streaming) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", content: q }, { role: "assistant", content: "" }]);
    setStreaming(true);
    try {
      const headers = await getApiAuthHeaders({ "Content-Type": "application/json" });
      const res = await fetch(`${API}/ask`, {
        method: "POST",
        headers,
        credentials: "include",
        body: JSON.stringify({ message: q }),
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
          setMessages((m) => {
            const copy = [...m];
            copy[copy.length - 1] = { role: "assistant", content: message };
            return copy;
          });
          return;
        }
        setMessages((m) => m.slice(0, -2));
        setStreaming(false);
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
        setMessages((m) => {
          const copy = [...m];
          copy[copy.length - 1] = { role: "assistant", content: `${detail} Open Billing to upgrade.` };
          return copy;
        });
        return;
      }
      if (!res.ok) {
        setMessages((m) => {
          const copy = [...m];
          copy[copy.length - 1] = { role: "assistant", content: "I couldn't reach my reasoning engine. Please try again." };
          return copy;
        });
        return;
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let acc = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        acc += decoder.decode(value, { stream: true });
        setMessages((m) => {
          const copy = [...m];
          copy[copy.length - 1] = { role: "assistant", content: acc };
          return copy;
        });
      }
    } catch (e) {
      setMessages((m) => {
        const copy = [...m];
        copy[copy.length - 1] = { role: "assistant", content: "I couldn't reach my reasoning engine. Please try again." };
        return copy;
      });
    } finally {
      setStreaming(false);
    }
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

  return (
    <div className="flex gap-6 h-[calc(100vh-8rem)] lg:h-[calc(100vh-6rem)]" data-testid="ask-trenston-layout">
      {/* Chat column */}
      <div className="flex flex-col flex-1 min-w-0 lg:w-[60%] lg:flex-none">
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          <p className="text-sm text-helm-muted">{empty ? "New chat" : "Ask Trenston"}</p>
          <div className="flex flex-wrap items-center gap-2">
            <button type="button" className="inline-flex items-center gap-1 rounded-full border border-helm-line px-3 py-1.5 text-xs text-helm-muted">
              This month <ChevronDown className="w-3 h-3" />
            </button>
            <button type="button" className="inline-flex items-center gap-1 rounded-full border border-helm-line px-3 py-1.5 text-xs text-helm-muted">
              All departments <ChevronDown className="w-3 h-3" />
            </button>
            <button
              type="button"
              className="inline-flex items-center gap-1.5 rounded-full border border-helm-line px-3 py-1.5 text-xs text-helm-fg hover:bg-helm-fg/[0.04]"
            >
              <Share2 className="w-3.5 h-3.5" /> Share
            </button>
            <button
              type="button"
              className="inline-flex items-center gap-1.5 rounded-full bg-helm-gold px-3 py-1.5 text-xs font-medium text-helm-navy hover:bg-helm-gold-hover"
            >
              <Download className="w-3.5 h-3.5" /> Export
            </button>
          </div>
        </div>

        <div ref={scrollRef} className="flex-1 overflow-y-auto pr-1 space-y-6">
          {empty && (
            <div className="max-w-xl mx-auto lg:mx-0 pt-6">
              <h1 className="font-display text-3xl text-helm-navy tracking-tight leading-tight">
                {timeGreet === "Hello"
                  ? `What's on your plate today, ${firstName}?`
                  : `${timeGreet}, ${firstName}. What's on your plate?`}
              </h1>
              <div className="mt-8">
                <div className="flex items-center gap-2 mb-4 text-helm-gold">
                  <Sparkles className="w-4 h-4" />
                  <span className="font-mono text-xs uppercase tracking-[0.2em]">Try asking</span>
                </div>
                <div className="grid sm:grid-cols-2 gap-2">
                  {suggestions.map((s) => (
                    <button
                      key={s}
                      type="button"
                      onClick={() => send(s)}
                      data-testid="ask-suggestion"
                      className="text-left rounded-lg border border-helm-line bg-helm-fg/[0.02] p-3 text-sm text-helm-fg transition-colors hover:border-helm-gold/35 hover:bg-helm-fg/[0.04]"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          )}

          {messages.map((m, i) => (
            <div key={i} className={cn("flex gap-3", m.role === "user" && "flex-row-reverse")} data-testid={`msg-${m.role}`}>
              <div className={cn(
                "w-7 h-7 rounded-md flex items-center justify-center shrink-0 border",
                m.role === "user" ? "bg-helm-fg/5 border-helm-line" : "bg-helm-gold/12 border-helm-gold/35",
              )}>
                {m.role === "user" ? <User className="w-3.5 h-3.5 text-helm-muted" /> : <span className="font-mono text-helm-gold text-xs">H</span>}
              </div>
              <div className={cn(
                "max-w-[80%] rounded-xl px-4 py-3 text-[15px] leading-relaxed",
                m.role === "user" ? "bg-helm-fg/5 border border-helm-line text-helm-fg" : "bg-helm-card border border-helm-line text-helm-fg",
              )}>
                {m.content ? <p className="whitespace-pre-wrap">{m.content}</p> : <AITextLoading />}
              </div>
            </div>
          ))}
        </div>

        <div className="mt-4 pt-4 border-t border-helm-line">
          <div className="flex items-center gap-2 rounded-xl border border-helm-line bg-helm-card px-2 py-2 focus-within:border-helm-gold/35 transition-colors">
            <button
              type="button"
              aria-label="Attach"
              className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-helm-muted hover:bg-helm-fg/[0.04] hover:text-helm-fg"
            >
              <Plus className="w-4 h-4" />
            </button>
            <input
              data-testid="ask-input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && send()}
              placeholder="Ask Trenston anything about your company…"
              className="flex-1 bg-transparent text-helm-fg text-sm placeholder:text-helm-muted focus:outline-none py-1.5"
            />
            <button
              data-testid="ask-send-btn"
              type="button"
              onClick={() => send()}
              disabled={streaming || !input.trim()}
              className="w-9 h-9 rounded-lg bg-helm-gold text-helm-navy flex items-center justify-center transition-colors hover:bg-helm-gold-hover disabled:opacity-40"
            >
              <Send className="w-4 h-4" />
            </button>
          </div>
          <p className="mt-2 text-center text-[11px] text-helm-muted">
            Trenston can make mistakes. Check important numbers.
          </p>
        </div>
      </div>

      {/* Right context rail */}
      <aside className="hidden lg:flex w-[40%] flex-col gap-6 overflow-y-auto pb-4" data-testid="ask-context-rail">
        <section>
          <div className="flex items-center justify-between mb-3">
            <span className="inline-flex items-center rounded-full border border-helm-line px-2.5 py-1 font-mono text-[10px] uppercase tracking-wider text-helm-muted">
              For you in {companyName}
            </span>
            <Link to="/app" className="text-xs text-helm-muted hover:text-helm-fg">View all</Link>
          </div>
          <div className="grid grid-cols-3 gap-2">
            {forYouCards.map((card) => {
              const Icon = card.icon;
              return (
                <button
                  key={card.title + card.caption}
                  type="button"
                  onClick={() => navigate(card.to)}
                  className="rounded-lg overflow-hidden border border-helm-line text-left transition-colors hover:border-helm-gold/35"
                >
                  <div className={cn("h-16 flex items-center justify-center", card.tone)}>
                    <Icon className="w-6 h-6" />
                  </div>
                  <div className="p-2.5">
                    <p className="text-xs font-medium text-helm-fg line-clamp-2 leading-snug">{card.title}</p>
                    <p className="mt-1 font-mono text-[9px] uppercase tracking-wider text-helm-muted">{card.caption}</p>
                  </div>
                </button>
              );
            })}
          </div>
        </section>

        <section>
          <p className="mb-3 text-sm font-medium text-helm-fg">Get started</p>
          <div className="grid grid-cols-3 gap-2">
            {GET_STARTED.map((tile) => {
              const Icon = tile.icon;
              return (
                <button
                  key={tile.label}
                  type="button"
                  onClick={() => navigate(tile.to)}
                  className={cn(
                    "relative h-28 rounded-lg overflow-hidden text-left transition-opacity hover:opacity-90",
                    tile.bg,
                  )}
                >
                  <Icon className="absolute right-2 top-2 w-8 h-8 text-white/25" />
                  <span className="absolute bottom-2.5 left-2.5 right-2 font-medium text-sm text-white leading-snug">
                    {tile.label}
                  </span>
                </button>
              );
            })}
          </div>
        </section>

        <section>
          <div className="flex items-center justify-between mb-3">
            <p className="text-sm font-medium text-helm-fg">Get inspired</p>
            <Link to="/app/reports" className="text-xs text-helm-muted hover:text-helm-fg">See all</Link>
          </div>
          <div className="grid grid-cols-3 gap-2">
            {inspiredCards.map((card, i) => (
              <button
                key={`${card.title}-${i}`}
                type="button"
                onClick={() => {
                  if (card.prompt) send(card.prompt);
                  else if (card.to) navigate(card.to);
                }}
                className="rounded-lg overflow-hidden border border-helm-line text-left transition-colors hover:border-helm-gold/35"
              >
                <div className="relative h-16 bg-helm-fg/[0.04] flex items-center justify-center">
                  <span className="absolute top-1.5 left-1.5 rounded-full bg-helm-card border border-helm-line px-1.5 py-0.5 text-[9px] text-helm-muted truncate max-w-[90%]">
                    {card.author}
                  </span>
                  <Sparkles className="w-5 h-5 text-helm-gold/60" />
                </div>
                <div className="p-2.5">
                  <p className="text-xs font-medium text-helm-fg line-clamp-2 leading-snug">{card.title}</p>
                  <p className="mt-1 text-[10px] text-helm-muted line-clamp-1">{card.caption}</p>
                </div>
              </button>
            ))}
          </div>
        </section>
      </aside>
    </div>
  );
}
