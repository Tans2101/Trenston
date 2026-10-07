import { isChunkLoadError, isOffline } from "@/lib/chunkReload";

/** Thrown by the API client when Clerk has not produced a session token yet. */
export const CLERK_TOKEN_TIMEOUT = "clerk-token-timeout";

export function isCanceledRequest(error) {
  return (
    error?.name === "CanceledError"
    || error?.name === "AbortError"
    || error?.code === "ERR_CANCELED"
  );
}

/**
 * Plain-language copy for request failures the server did not explain.
 * Returns null when there is nothing better to say than the caller's own fallback.
 */
export function friendlyRequestError(error) {
  if (!error || typeof error !== "object") return null;
  if (error.message === CLERK_TOKEN_TIMEOUT) {
    return "Sign-in is still loading. Wait a moment and try again.";
  }
  if (!error.isAxiosError || isCanceledRequest(error)) return null;
  if (error.code === "ECONNABORTED" || error.code === "ETIMEDOUT" || /timeout/i.test(error.message || "")) {
    return "Request timed out. The server may be busy. Try again.";
  }
  const status = error.response?.status;
  if (!status) {
    return isOffline()
      ? "You're offline. Check your connection and try again."
      : "Couldn't reach Trenston. Check your connection and try again.";
  }
  if (status === 401) return "Your session has expired. Sign in again to continue.";
  if (status === 403) return "You don't have access to this. Check your plan or ask a workspace admin.";
  if (status === 404) return "We couldn't find that. It may have been moved or deleted.";
  if (status === 413) return "That file is too large to upload.";
  if (status === 429) return "Too many requests. Wait a moment and try again.";
  if (status >= 500) return "Trenston is having trouble right now. Try again in a few seconds.";
  return null;
}

/** Whether an uncaught error is worth a toast. Browser noise and handled cases are not. */
export function shouldReportGlobalError(error, message = error?.message) {
  const text = String(message || "");
  if (/ResizeObserver loop/i.test(text)) return false;
  // Cross-origin script failure with no detail; nothing the user can act on.
  if (text === "Script error." || text === "Script error") return false;
  if (isCanceledRequest(error)) return false;
  // lazyWithReload and ErrorBoundary already handle missing chunks after a deploy.
  if (isChunkLoadError(error)) return false;
  return true;
}
