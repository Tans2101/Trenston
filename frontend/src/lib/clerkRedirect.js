import { CLERK_AFTER_AUTH_PATH as AFTER_AUTH_FROM_ENV } from "@/lib/helmUrls";

/** Same-origin path Clerk should send users to after a complete session. */
export const CLERK_AFTER_AUTH_PATH = AFTER_AUTH_FROM_ENV;

/**
 * Clerk only accepts forceRedirectUrl values on the instance allow list.
 * Prefer a same-origin path so www vs apex cannot produce a rejected URL.
 * Absolute URLs are used only for true multi-domain (satellite) setups.
 */
export function clerkAfterAuthRedirect(config) {
  const cfg = config || {};
  if (cfg.clerk_multi_domain || cfg.clerkMultiDomain) {
    return String(cfg.clerk_post_auth_url || cfg.postAuthUrl || CLERK_AFTER_AUTH_PATH);
  }
  return CLERK_AFTER_AUTH_PATH;
}
