/**
 * @author: @kokonutui / Trenston
 * @description: Action Search Bar — ⌘K quick nav (KokonutUI, restyled)
 * @website: https://kokonutui.com
 *
 * Variants:
 * - dialog: full-screen centered modal (mobile)
 * - inline: pill input in the desktop top bar with an anchored panel
 */

import { ArrowUpRight, Search } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import { Input } from "@/components/ui/input";
import useDebounce from "@/hooks/use-debounce";
import { cn } from "@/lib/utils";

const DEFAULT_QUICK_IDS = ["myday", "briefing", "calendar", "ask", "reports"];

/**
 * @param {{ id: string, label: string, icon?: React.ReactNode, description?: string, to?: string }[]} actions
 * @param {(action) => void} onSelect
 * @param {boolean} open
 * @param {(open: boolean) => void} onOpenChange
 * @param {"dialog"|"inline"} variant
 * @param {{ id: string }[]} [quickActions] curated empty-state chips
 * @param {{ id: string }[]} [departmentActions] empty-state department cards
 * @param {boolean} [enableShortcut] dialog ⌘K (default true); AppLayout disables when owning the shortcut
 */
const ActionSearchBar = forwardRef(function ActionSearchBar(
  {
    actions = [],
    onSelect,
    open: controlledOpen,
    onOpenChange,
    variant = "dialog",
    quickActions,
    departmentActions,
    enableShortcut = true,
  },
  ref,
) {
  const reduceMotion = useReducedMotion();
  const [internalOpen, setInternalOpen] = useState(false);
  const isControlled = controlledOpen !== undefined;
  const isOpen = isControlled ? controlledOpen : internalOpen;
  const setOpen = useCallback(
    (next) => {
      if (!isControlled) setInternalOpen(next);
      onOpenChange?.(next);
    },
    [isControlled, onOpenChange],
  );

  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef(null);
  const rootRef = useRef(null);
  const debouncedQuery = useDebounce(query, 150);
  const isInline = variant === "inline";
  const isMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform || "");

  const filtered = useMemo(() => {
    if (!debouncedQuery.trim()) return isInline ? [] : actions;
    const q = debouncedQuery.toLowerCase().trim();
    return actions.filter((a) => {
      const haystack = [
        a.label,
        a.description,
        ...(Array.isArray(a.keywords) ? a.keywords : []),
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return haystack.includes(q);
    });
  }, [actions, debouncedQuery, isInline]);

  const emptyQuick = useMemo(() => {
    if (quickActions?.length) return quickActions;
    const byId = new Map(actions.map((a) => [a.id, a]));
    return DEFAULT_QUICK_IDS.map((id) => byId.get(id)).filter(Boolean);
  }, [actions, quickActions]);

  const emptyDepts = useMemo(() => {
    if (departmentActions?.length) return departmentActions;
    return actions.filter((a) => a.description === "Department");
  }, [actions, departmentActions]);

  const showBrowse = isInline && isOpen && !debouncedQuery.trim();
  const showResults = !isInline || Boolean(debouncedQuery.trim());

  useImperativeHandle(ref, () => ({
    focus: () => {
      setOpen(true);
      requestAnimationFrame(() => inputRef.current?.focus());
    },
    open: () => {
      setOpen(true);
      requestAnimationFrame(() => inputRef.current?.focus());
    },
  }), [setOpen]);

  // Global ⌘K — optional on dialog; inline is focused from AppLayout.
  useEffect(() => {
    if (isInline || !enableShortcut) return undefined;
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen(!isOpen);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isInline, enableShortcut, isOpen, setOpen]);

  useEffect(() => {
    if (!isOpen) {
      setQuery("");
      setActiveIndex(0);
      return;
    }
    const t = requestAnimationFrame(() => inputRef.current?.focus());
    return () => cancelAnimationFrame(t);
  }, [isOpen]);

  useEffect(() => {
    setActiveIndex(0);
  }, [debouncedQuery]);

  // Click-outside for inline panel (backdrop also closes).
  useEffect(() => {
    if (!isInline || !isOpen) return undefined;
    const onPointer = (e) => {
      if (rootRef.current && !rootRef.current.contains(e.target)) {
        setOpen(false);
        inputRef.current?.blur();
      }
    };
    document.addEventListener("mousedown", onPointer);
    return () => document.removeEventListener("mousedown", onPointer);
  }, [isInline, isOpen, setOpen]);

  const choose = useCallback(
    (action) => {
      if (!action) return;
      onSelect?.(action);
      setOpen(false);
      setQuery("");
      inputRef.current?.blur();
    },
    [onSelect, setOpen],
  );

  const onKeyDown = (e) => {
    if (e.key === "Escape") {
      e.preventDefault();
      setOpen(false);
      inputRef.current?.blur();
      return;
    }
    if (!showResults || !filtered.length) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => (i + 1) % filtered.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => (i - 1 + filtered.length) % filtered.length);
    } else if (e.key === "Enter") {
      e.preventDefault();
      choose(filtered[activeIndex]);
    }
  };

  const resultsList = (
    <ul role="listbox" className={cn("overflow-y-auto py-1", isInline ? "max-h-80" : "max-h-72")}>
      {filtered.length === 0 ? (
        <li className="px-3 py-6 text-center text-sm text-helm-muted">No matches</li>
      ) : (
        filtered.map((action, i) => (
          <li key={action.id} role="option" aria-selected={i === activeIndex}>
            <button
              type="button"
              id={`action-${action.id}`}
              className={cn(
                "w-full flex items-center gap-3 px-3 py-2.5 text-left text-sm transition-colors",
                i === activeIndex
                  ? "bg-helm-gold/12 text-helm-fg"
                  : "text-helm-fg hover:bg-helm-fg/[0.04]",
              )}
              onMouseEnter={() => setActiveIndex(i)}
              onClick={() => choose(action)}
            >
              <span className={cn("shrink-0", i === activeIndex ? "text-helm-gold" : "text-helm-muted")}>
                {action.icon}
              </span>
              <span className="truncate flex-1">{action.label}</span>
              {action.description ? (
                <span className="text-[10px] font-mono uppercase tracking-wider text-helm-muted shrink-0">
                  {action.description}
                </span>
              ) : null}
            </button>
          </li>
        ))
      )}
    </ul>
  );

  const browsePanel = (
    <div className="p-3 space-y-4 max-h-[min(70vh,28rem)] overflow-y-auto" data-testid="action-search-browse">
      {emptyQuick.length > 0 && (
        <section>
          <p className="text-[10px] font-mono uppercase tracking-wider text-helm-muted px-1 mb-2">
            Quick actions
          </p>
          <div className="flex flex-wrap gap-2">
            {emptyQuick.map((action) => (
              <button
                key={action.id}
                type="button"
                data-testid={`action-search-chip-${action.id}`}
                onClick={() => choose(action)}
                className="inline-flex items-center gap-1.5 rounded-full border border-helm-line bg-helm-fg/[0.03] px-3 py-1.5 text-sm text-helm-fg transition-colors hover:border-helm-gold/35 hover:bg-helm-gold/10"
              >
                <ArrowUpRight className="w-3.5 h-3.5 text-helm-muted shrink-0" />
                <span className="truncate max-w-[10rem]">{action.label}</span>
              </button>
            ))}
          </div>
        </section>
      )}
      {emptyDepts.length > 0 && (
        <section>
          <p className="text-[10px] font-mono uppercase tracking-wider text-helm-muted px-1 mb-2">
            Departments
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {emptyDepts.map((action) => (
              <button
                key={action.id}
                type="button"
                data-testid={`action-search-dept-${action.id}`}
                onClick={() => choose(action)}
                className="flex items-center gap-2.5 rounded-lg border border-helm-line bg-helm-fg/[0.03] px-3 py-2.5 text-left text-sm text-helm-fg transition-colors hover:border-helm-gold/35 hover:bg-helm-gold/10"
              >
                <span className="shrink-0 text-helm-muted">{action.icon}</span>
                <span className="truncate font-medium">{action.label}</span>
              </button>
            ))}
          </div>
        </section>
      )}
      {emptyQuick.length === 0 && emptyDepts.length === 0 && (
        <p className="px-1 py-4 text-center text-sm text-helm-muted">Start typing to search</p>
      )}
    </div>
  );

  if (isInline) {
    return (
      <div ref={rootRef} className="relative w-full max-w-xl" data-testid="action-search-bar-inline">
        <div
          className={cn(
            "flex items-center gap-2 rounded-full border bg-helm-fg/[0.03] pl-3.5 pr-3 h-10 transition-colors",
            isOpen
              ? "border-helm-gold/40 bg-helm-card shadow-sm"
              : "border-helm-line hover:border-helm-fg/20",
          )}
        >
          <Search className="w-4 h-4 text-helm-muted shrink-0 pointer-events-none" />
          <Input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onFocus={() => setOpen(true)}
            onKeyDown={onKeyDown}
            placeholder="Search Trenston…"
            data-testid="action-search-input"
            className="h-9 flex-1 border-0 rounded-none bg-transparent px-0 text-sm text-helm-fg placeholder:text-helm-muted focus-visible:ring-0 shadow-none"
            autoComplete="off"
            role="combobox"
            aria-expanded={isOpen}
            aria-autocomplete="list"
          />
          <kbd className="hidden sm:inline font-mono text-[10px] text-helm-muted border border-helm-line rounded-full px-1.5 py-0.5 shrink-0">
            {isMac ? "⌘K" : "Ctrl+K"}
          </kbd>
        </div>

        <AnimatePresence>
          {isOpen && (
            <>
              {/* Dim page content only — sidebar + this top bar stay clear */}
              <motion.div
                className="fixed inset-0 top-14 left-0 lg:left-[220px] z-30 bg-helm-ink/35"
                initial={reduceMotion ? false : { opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.15 }}
                onClick={() => setOpen(false)}
                aria-hidden
                data-testid="action-search-backdrop"
              />
              <motion.div
                role="dialog"
                aria-label="Quick navigation"
                className="absolute left-0 right-0 top-[calc(100%+0.5rem)] z-40 rounded-xl border border-helm-line bg-helm-card shadow-2xl overflow-hidden min-w-[min(100%,28rem)] sm:min-w-[28rem]"
                initial={reduceMotion ? false : { opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 4 }}
                transition={{ duration: 0.16, ease: [0.16, 1, 0.3, 1] }}
                data-testid="action-search-panel"
              >
                {showBrowse ? browsePanel : resultsList}
                <div className="border-t border-helm-line px-3 py-2 flex items-center justify-between text-[10px] font-mono uppercase tracking-wider text-helm-muted">
                  <span>{showBrowse ? "Browse" : "Navigate"}</span>
                  <span>esc</span>
                </div>
              </motion.div>
            </>
          )}
        </AnimatePresence>
      </div>
    );
  }

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4" data-testid="action-search-bar">
          <motion.div
            className="absolute inset-0 bg-helm-ink/60"
            initial={reduceMotion ? false : { opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            onClick={() => setOpen(false)}
            aria-hidden
          />
          <motion.div
            role="dialog"
            aria-label="Quick navigation"
            className="relative z-[1] w-[min(100%,28rem)] rounded-lg border border-helm-line bg-helm-card shadow-2xl overflow-hidden"
            initial={reduceMotion ? false : { opacity: 0, y: 8, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 6, scale: 0.98 }}
            transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
          >
            <div className="relative border-b border-helm-line">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-helm-muted pointer-events-none" />
              <Input
                ref={inputRef}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={onKeyDown}
                placeholder="Go to…"
                data-testid="action-search-input"
                className="h-11 border-0 rounded-none bg-transparent pl-10 pr-16 text-sm text-helm-fg placeholder:text-helm-muted focus-visible:ring-0 shadow-none"
                autoComplete="off"
                role="combobox"
                aria-expanded
                aria-autocomplete="list"
              />
              <kbd className="absolute right-3 top-1/2 -translate-y-1/2 font-mono text-[10px] text-helm-muted border border-helm-line rounded px-1.5 py-0.5">
                esc
              </kbd>
            </div>
            {resultsList}
            <div className="border-t border-helm-line px-3 py-2 flex items-center justify-between text-[10px] font-mono uppercase tracking-wider text-helm-muted">
              <span>Navigate</span>
              <span>⌘K</span>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
});

export default ActionSearchBar;
