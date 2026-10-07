import { lazy } from "react";

const RELOAD_KEY = "trenston_chunk_reload_at";
// A second chunk failure within this window means a reload did not help; stop reloading.
const RELOAD_WINDOW_MS = 30_000;

/** True when a lazy page's JS/CSS file is gone, usually because a newer deploy replaced it. */
export function isChunkLoadError(error) {
  if (!error) return false;
  const name = String(error.name || "");
  const message = String(error.message || "");
  return (
    name === "ChunkLoadError"
    || /Loading (CSS )?chunk [\w-]+ failed/i.test(message)
    || /dynamically imported module/i.test(message)
  );
}

export function isOffline() {
  return typeof navigator !== "undefined" && navigator.onLine === false;
}

function sessionStore() {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

/** Reloads to pick up the latest deploy. Returns false (no reload) if one just happened. */
export function reloadForNewVersion({
  storage = sessionStore(),
  reload = () => window.location.reload(),
  now = Date.now(),
  offline = isOffline(),
} = {}) {
  // Reloading offline only swaps the error for the browser's "no internet" page.
  if (offline || !storage) return false;
  try {
    const last = Number(storage.getItem(RELOAD_KEY) || 0);
    if (now - last < RELOAD_WINDOW_MS) return false;
    storage.setItem(RELOAD_KEY, String(now));
  } catch {
    return false;
  }
  reload();
  return true;
}

/** React.lazy that reloads once when the page's chunk is missing after a deploy. */
export function lazyWithReload(factory) {
  return lazy(() =>
    factory().catch((error) => {
      if (isChunkLoadError(error) && reloadForNewVersion()) {
        // Keep the Suspense fallback on screen while the page reloads.
        return new Promise(() => {});
      }
      throw error;
    }),
  );
}
