/** Open a warm TLS connection to Clerk before the widget needs it. */

const CLERK_ORIGIN = "https://clerk.trenston.com";

export function ensureClerkPreconnect() {
  if (typeof document === "undefined") return;
  if (document.querySelector(`link[data-helm-clerk-preconnect="1"]`)) return;
  const link = document.createElement("link");
  link.rel = "preconnect";
  link.href = CLERK_ORIGIN;
  link.crossOrigin = "anonymous";
  link.setAttribute("data-helm-clerk-preconnect", "1");
  document.head.appendChild(link);
}
