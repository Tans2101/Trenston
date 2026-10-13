import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { guideById } from "@/lib/pageGuides";
import TourOverlay from "@/components/guide/TourOverlay";

const LOCAL_KEY = "trenston.guides.v1";
export const TIPS_OFF = "tips-off";
export const GUIDES_CHANGED_EVENT = "trenston:guides-changed";
export const OPEN_SEARCH_EVENT = "trenston:open-search";

function readLocal() {
  try {
    const raw = window.localStorage.getItem(LOCAL_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function writeLocal(value) {
  try {
    window.localStorage.setItem(LOCAL_KEY, JSON.stringify(value));
  } catch {
    /* private mode or storage blocked: the server copy still works */
  }
}

const GuideContext = createContext({
  seen: {},
  isSeen: () => true,
  markSeen: () => {},
  startTour: () => {},
  resetAll: () => {},
  activeTour: null,
  helpOpen: false,
  setHelpOpen: () => {},
  checklistShowing: false,
  setChecklistShowing: () => {},
});

export const useGuides = () => useContext(GuideContext);

/** Ask the shell to open the search bar, optionally pre-filled (used by the quick-add tour). */
export function openSearch(text = "") {
  window.dispatchEvent(new CustomEvent(OPEN_SEARCH_EVENT, { detail: { text } }));
}

export function GuideProvider({ children }) {
  const { user, setUser } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [local, setLocal] = useState(readLocal);
  const [active, setActive] = useState(null); // { id, step }
  const [pending, setPending] = useState(null); // guide id waiting for its page to open
  const [helpOpen, setHelpOpen] = useState(false);
  const [checklistShowing, setChecklistShowing] = useState(false);

  const seen = useMemo(() => ({ ...(user?.guides_seen || {}), ...local }), [user?.guides_seen, local]);
  const isSeen = useCallback((id) => Boolean(seen[id]), [seen]);

  const markSeen = useCallback((id) => {
    if (!id) return;
    const now = new Date().toISOString();
    setLocal((prev) => {
      const next = { ...prev, [id]: now };
      writeLocal(next);
      return next;
    });
    setUser?.((prev) => (prev ? { ...prev, guides_seen: { ...(prev.guides_seen || {}), [id]: now } } : prev));
    api.patch("/account/guides", { guide_id: id })
      .catch(() => {})
      .finally(() => window.dispatchEvent(new Event(GUIDES_CHANGED_EVENT)));
  }, [setUser]);

  const resetAll = useCallback(async () => {
    setLocal({});
    writeLocal({});
    setUser?.((prev) => (prev ? { ...prev, guides_seen: {} } : prev));
    try {
      await api.patch("/account/guides", { reset_all: true });
    } catch {
      /* local reset still applies on this device */
    }
    window.dispatchEvent(new Event(GUIDES_CHANGED_EVENT));
    toast.success("Page tips are back on");
  }, [setUser]);

  const startTour = useCallback((id, { route } = {}) => {
    const guide = guideById(id);
    if (!guide) return;
    setHelpOpen(false);
    markSeen(id);
    const here = guide.path ? guide.path.test(location.pathname.replace(/\/+$/, "") || "/") : true;
    if (route && location.pathname !== route && !here) {
      setPending(id);
      navigate(route);
      return;
    }
    setActive({ id, step: 0 });
  }, [location.pathname, markSeen, navigate]);

  useEffect(() => {
    if (!pending) return;
    const guide = guideById(pending);
    const path = location.pathname.replace(/\/+$/, "") || "/";
    if (!guide?.path || guide.path.test(path)) {
      setActive({ id: pending, step: 0 });
      setPending(null);
    }
  }, [pending, location.pathname]);

  // Leaving the page ends its tour (the buttons it points at are gone).
  useEffect(() => {
    setActive((cur) => {
      if (!cur) return cur;
      const g = guideById(cur.id);
      const path = location.pathname.replace(/\/+$/, "") || "/";
      return g?.path && !g.path.test(path) ? null : cur;
    });
  }, [location.pathname]);

  const guide = active ? guideById(active.id) : null;
  const close = useCallback((finished) => {
    setActive(null);
    if (finished) toast("Tour done. Press ? at the top of any page to see help again.");
  }, []);

  const value = useMemo(() => ({
    seen, isSeen, markSeen, startTour, resetAll, activeTour: active, helpOpen, setHelpOpen,
    checklistShowing, setChecklistShowing,
  }), [seen, isSeen, markSeen, startTour, resetAll, active, helpOpen, checklistShowing]);

  return (
    <GuideContext.Provider value={value}>
      {children}
      {guide && guide.steps.length > 0 && (
        <TourOverlay
          guide={guide}
          stepIndex={active.step}
          onBack={() => setActive((c) => ({ ...c, step: Math.max(0, c.step - 1) }))}
          onNext={() => {
            if (active.step >= guide.steps.length - 1) close(true);
            else setActive((c) => ({ ...c, step: c.step + 1 }));
          }}
          onClose={() => close(false)}
          onTry={(text) => {
            close(false);
            window.setTimeout(() => openSearch(text), 60);
          }}
        />
      )}
    </GuideContext.Provider>
  );
}
