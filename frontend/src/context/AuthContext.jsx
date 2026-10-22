import { createContext, useContext, useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";
import { clearClerkTokenCache } from "@/lib/clerkToken";

const AuthContext = createContext(null);

export function AuthProvider({ children, onLogoutExtra, deferInitialAuth = false }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [sessionError, setSessionError] = useState("");

  /**
   * Refresh the Trenston session from `/auth/me`.
   * Soft mode (WorkspaceGate focus refresh) must not clear a good session on
   * transient network/401 blips — that kicked signed-in users to login.
   */
  const checkAuth = useCallback(async (opts = {}) => {
    const soft = Boolean(opts?.soft);
    try {
      const { data } = await api.get("/auth/me");
      setUser(data);
      setSessionError("");
      return data;
    } catch (e) {
      if (!soft) setUser(null);
      throw e;
    } finally {
      setLoading(false);
    }
  }, []);

  const clearSessionError = useCallback(() => setSessionError(""), []);

  useEffect(() => {
    if (window.location.hash?.includes("session_id=")) {
      setLoading(false);
      return;
    }
    if (deferInitialAuth) {
      // ClerkHelmBridge owns the first /auth/me (via exchange); don't double-fetch.
      setLoading(false);
      return;
    }
    let cancelled = false;
    const watchdog = setTimeout(() => {
      if (!cancelled) setLoading(false);
    }, 12000);
    checkAuth().catch(() => {}).finally(() => {
      cancelled = true;
      clearTimeout(watchdog);
    });
    return () => {
      cancelled = true;
      clearTimeout(watchdog);
    };
  }, [checkAuth, deferInitialAuth]);

  const logout = async () => {
    try { await api.post("/auth/logout"); } catch (e) {}
    clearClerkTokenCache();
    setUser(null);
    setSessionError("");
    if (onLogoutExtra) {
      try { await onLogoutExtra(); } catch (e) {}
    }
    window.location.href = "/login";
  };

  return (
    <AuthContext.Provider value={{
      user, setUser, loading, checkAuth, logout, sessionError, setSessionError, clearSessionError,
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
