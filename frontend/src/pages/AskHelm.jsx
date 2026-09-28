import { useState, useEffect, useRef } from "react";
import { Send, Sparkles, User, ArrowUpRight } from "lucide-react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { useFetch, useInvalidateFetch } from "@/hooks/useFetch";
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

const ENGINE_ERROR = "I couldn't reach my reasoning engine. Please try again.";
const EMPTY_ANSWER = "No answer came back. Try again.";

/** Replace the pending (last) assistant message. */
const replaceLast = (msg) => (m) => {
  const copy = [...m];
  copy[copy.length - 1] = { role: "assistant", ...msg };
  return copy;
};

export default function AskHelm() {
  const { user } = useAuth();
  const { data: company } = useCompanyQuery();
  const { data: history } = useFetch("/ask/history");
  const invalidateFetch = useInvalidateFetch();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const scrollRef = useRef(null);
  const autoSent = useRef(false);
  // True once the user sends in this visit; from then on local state owns the thread.
  const sentThisVisit = useRef(false);
  const navigate = useNavigate();
  const location = useLocation();
  const canSeeFinancials = (user?.granted_sections || []).includes("financials");
  const suggestions = SUGGESTIONS.filter(
    (s) => canSeeFinancials || !FINANCE_SUGGESTION_RE.test(s),
  );
  const firstName = (user?.name || company?.ceo_name || "there").split(" ")[0];
  const { greeting: timeGreet } = dayPartGreeting();

  useEffect(() => {
    // Mirror server history until the user sends in this visit. The cache can hand
    // us a stale copy first and the fresh one a moment later, so keep applying
    // updates rather than locking in whichever arrived first. Never overwrite an
    // in-flight or already-started chat.
    if (sentThisVisit.current || streaming) return;
    if (!history?.messages) return;
    setMessages(history.messages.map((m) => ({ role: m.role, content: m.content, isError: Boolean(m.is_error) })));
  }, [history, streaming]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, streaming]);

  const send = async (text) => {
    const q = (text ?? input).trim();
    if (!q || streaming) return;
    sentThisVisit.current = true;
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
          setMessages(replaceLast({ content: message, isError: true }));
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
        setMessages(replaceLast({
          content: detail,
          isError: true,
          link: { to: "/app/billing", label: "Open Billing to upgrade" },
        }));
        return;
      }
      if (!res.ok || !res.body) {
        setMessages(replaceLast({ content: ENGINE_ERROR, isError: true }));
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
      const tail = decoder.decode();
      if (tail) {
        acc += tail;
        setMessages(replaceLast({ content: acc }));
      }
      // An empty stream would otherwise leave the loading indicator up forever.
      if (!acc.trim()) setMessages(replaceLast({ content: EMPTY_ANSWER, isError: true }));
    } catch (e) {
      setMessages(replaceLast({ content: ENGINE_ERROR, isError: true }));
    } finally {
      setStreaming(false);
      // POST /ask goes through fetch, not the api client, so drop the cached
      // history here; coming back to this page then shows the latest exchange.
      invalidateFetch("/ask/history");
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
    <div className="flex flex-col h-[calc(100vh-8rem)] lg:h-[calc(100vh-6rem)] max-w-3xl mx-auto w-full" data-testid="ask-trenston-layout">
      <div className="mb-4">
        <h1 className="font-display text-xl text-helm-navy tracking-tight">Ask Trenston</h1>
        <p className="mt-1 text-sm text-helm-muted">Answers grounded in your live company data.</p>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto pr-1 space-y-6">
        {empty && (
          <div className="pt-4">
            <h2 className="font-display text-2xl md:text-3xl text-helm-navy tracking-tight leading-tight">
              {timeGreet === "Hello"
                ? `What's on your plate today, ${firstName}?`
                : `${timeGreet}, ${firstName}. What's on your plate?`}
            </h2>
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
          <div key={i} className={cn("flex gap-3", m.role === "user" && "flex-row-reverse")} data-testid={m.isError ? "msg-error" : `msg-${m.role}`}>
            <div className={cn(
              "w-7 h-7 rounded-md flex items-center justify-center shrink-0 border",
              m.role === "user" ? "bg-helm-fg/5 border-helm-line" : "bg-helm-gold/12 border-helm-gold/35",
            )}>
              {m.role === "user" ? <User className="w-3.5 h-3.5 text-helm-muted" /> : <span className="font-mono text-helm-gold text-xs">T</span>}
            </div>
            <div className={cn(
              "max-w-[80%] rounded-xl px-4 py-3 text-[15px] leading-relaxed",
              m.role === "user"
                ? "bg-helm-fg/5 border border-helm-line text-helm-fg"
                : m.isError
                  ? "bg-helm-status-negative/5 border border-helm-status-negative/25 text-helm-muted italic"
                  : "bg-helm-card border border-helm-line text-helm-fg",
            )}>
              {m.content ? <p className="whitespace-pre-wrap">{m.content}</p> : <AITextLoading />}
              {m.link && (
                <Link
                  to={m.link.to}
                  data-testid="ask-message-link"
                  className="mt-2 inline-flex items-center gap-1 text-sm not-italic font-medium text-helm-gold hover:text-helm-gold-hover"
                >
                  {m.link.label} <ArrowUpRight className="w-3.5 h-3.5" />
                </Link>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="mt-4 pt-4 border-t border-helm-line">
        <div className="flex items-center gap-2 rounded-xl border border-helm-line bg-helm-card px-2 py-2 focus-within:border-helm-gold/35 transition-colors">
          <input
            data-testid="ask-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && send()}
            placeholder="Ask Trenston anything about your company…"
            className="flex-1 bg-transparent text-helm-fg text-sm placeholder:text-helm-muted focus:outline-none py-1.5 px-2"
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
  );
}
