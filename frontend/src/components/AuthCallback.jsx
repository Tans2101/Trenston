import { useEffect, useRef } from "react";
import { api } from "@/lib/api";

/**
 * Legacy Emergent hash callback (`#session_id=`). Production Google OAuth sets
 * the session cookie on /api/auth/google/callback and redirects to /app directly.
 */
export default function AuthCallback() {
  const hasProcessed = useRef(false);

  useEffect(() => {
    if (hasProcessed.current) return;
    hasProcessed.current = true;
    const hash = window.location.hash || "";
    const sid = new URLSearchParams(hash.replace(/^#/, "")).get("session_id");
    (async () => {
      if (!sid) {
        window.location.replace("/login");
        return;
      }
      try {
        await api.post("/auth/session", { session_id: sid });
        const { data } = await api.get("/auth/me");
        window.location.replace(data?.default_route || "/app");
      } catch (e) {
        window.location.replace("/login?error=session");
      }
    })();
  }, []);

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-helm-bg">
      <div className="w-8 h-8 rounded-full border-2 border-helm-gold/35 border-t-helm-gold animate-spin mb-6" />
      <p className="font-mono text-xs uppercase tracking-[0.3em] text-helm-gold">Trenston</p>
      <p className="text-helm-muted text-sm mt-2">Finishing sign-in…</p>
    </div>
  );
}
