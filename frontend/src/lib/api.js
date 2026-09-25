import axios from "axios";
import { invalidateFetchAfterMutation } from "@/lib/fetchInvalidation";

/** Empty string = same-origin `/api` (Vercel rewrite → Render). Local: http://localhost:8001 */
export const BACKEND_URL = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/$/, "");
export const API = BACKEND_URL ? `${BACKEND_URL}/api` : "/api";

export const api = axios.create({
  baseURL: API,
  withCredentials: true,
  timeout: 20000,
});

/** Normalize FastAPI `detail` (string | {message, reason} | validation list) for UI copy. */
export function apiErrorMessage(detailOrError, fallback = "Something went wrong") {
  const detail = detailOrError?.response?.data?.detail ?? detailOrError?.detail ?? detailOrError;
  if (typeof detail === "string" && detail.trim()) return detail;
  if (detail && typeof detail === "object") {
    if (typeof detail.message === "string" && detail.message.trim()) return detail.message;
    if (Array.isArray(detail)) {
      const parts = detail
        .map((item) => (typeof item === "string" ? item : item?.msg || item?.message))
        .filter(Boolean);
      if (parts.length) return parts.join("; ");
    }
  }
  if (typeof detailOrError?.message === "string" && detailOrError.message.trim()) {
    return detailOrError.message;
  }
  return fallback;
}

/** `permission` | `plan` | null from a 403 body (Ask Trenston, billing gates). */
export function apiForbiddenReason(detailOrBody) {
  const detail = detailOrBody?.detail ?? detailOrBody?.response?.data?.detail ?? detailOrBody;
  if (detail && typeof detail === "object" && !Array.isArray(detail) && detail.reason) {
    return String(detail.reason);
  }
  if (typeof detail === "string") {
    if (/permission/i.test(detail)) return "permission";
    if (/plan|upgrade|isn't included/i.test(detail)) return "plan";
  }
  return null;
}

let clerkGetToken = null;

const BOOTSTRAP_PATHS = ["/auth/me", "/auth/config"];

function isBootstrapPath(url) {
  const path = String(url || "").split("?")[0];
  return BOOTSTRAP_PATHS.some((p) => path === p || path.startsWith(`${p}/`));
}

/** Register Clerk getToken so every API call can send the session JWT. */
export function setClerkTokenGetter(getter) {
  clerkGetToken = getter;
}

/** Bearer headers for raw fetch (SSE streams that cannot use axios). */
export async function getApiAuthHeaders(extra = {}) {
  const headers = { ...extra };
  if (!clerkGetToken) return headers;
  const token = await clerkGetToken();
  if (!token) throw new Error("clerk-token-timeout");
  headers.Authorization = `Bearer ${token}`;
  return headers;
}

api.interceptors.request.use(async (config) => {
  config.headers = config.headers || {};
  // Caller already attached a Bearer token (e.g. Clerk exchange) — don't override/block.
  if (config.headers.Authorization) return config;
  if (!clerkGetToken) return config;
  const url = config.url || "";
  if (isBootstrapPath(url)) return config;
  try {
    // getCachedClerkToken already bounds Clerk refreshes and falls back to a
    // still-valid JWT. Do not wrap another short Promise.race here — a 1.5s
    // outer timeout was aborting legitimate refreshes (session + getToken can
    // each take up to 1.5s) and surfacing as "Could not save" on Financials.
    const token = await clerkGetToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
      return config;
    }
    // No token yet — fail instead of sending an unauthenticated call that 401s
    // and flips soft-reload pages into ErrorScreen.
    return Promise.reject(new Error("clerk-token-timeout"));
  } catch (err) {
    const msg = err?.message || "clerk-token-timeout";
    return Promise.reject(new Error(msg === "clerk-token-timeout" ? msg : "clerk-token-timeout"));
  }
});

// Structured 403 bodies ({reason, message}) stay toast-friendly as a string detail.
// Successful writes invalidate matching useFetch react-query caches immediately.
api.interceptors.response.use(
  (response) => {
    try {
      invalidateFetchAfterMutation(response?.config?.method, response?.config?.url);
    } catch {
      /* never block the response on cache invalidation */
    }
    return response;
  },
  (error) => {
    const data = error?.response?.data;
    const detail = data?.detail;
    // Always coerce detail to a string so toast.error(detail) never crashes React
    // (FastAPI validation lists / {message, reason} objects are not valid children).
    if (detail != null && typeof detail !== "string") {
      const reason =
        detail && typeof detail === "object" && !Array.isArray(detail)
          ? detail.reason ?? data.reason
          : data?.reason;
      error.response.data = {
        ...data,
        detail: apiErrorMessage(error, "Something went wrong"),
        reason,
        feature: (detail && typeof detail === "object" && !Array.isArray(detail) && detail.feature) || data?.feature,
      };
    }
    return Promise.reject(error);
  },
);

/** Fetch auth config without Clerk token (bootstrap). 30s cap — hung Render must not block forever. */
export async function fetchAuthConfig() {
  const { data } = await axios.get(`${API}/auth/config`, {
    withCredentials: true,
    timeout: 30000,
  });
  return data;
}

export { isBootstrapPath };
