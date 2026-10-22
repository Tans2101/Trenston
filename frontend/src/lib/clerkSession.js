/** True when Clerk has an active session (including pending right after email verify). */
export function clerkSessionActive({
  isSignedIn,
  userId,
  sessionId,
  session,
  sessionStatus,
}) {
  return Boolean(
    isSignedIn
    || userId
    || sessionId
    || session
    || sessionStatus === "pending",
  );
}

/** True when Clerk session is ready for Trenston JWT exchange (needs a concrete session). */
export function clerkSessionReadyForExchange({
  isSignedIn,
  userId,
  sessionId,
  session,
}) {
  return Boolean(isSignedIn || userId || sessionId || session);
}

/**
 * Fully signed-in Clerk session — not waiting on email/phone verification.
 * Pending sessions must keep the SignUp/SignIn widgets mounted.
 */
export function clerkSessionComplete({
  isSignedIn,
  userId,
  sessionId,
  session,
  sessionStatus,
}) {
  if (sessionStatus === "pending") return false;
  return clerkSessionReadyForExchange({ isSignedIn, userId, sessionId, session });
}

/** Clerk useAuth options — pending sessions must count as signed in for Trenston exchange. */
export const CLERK_AUTH_OPTS = { treatPendingAsSignedOut: false };

/**
 * When Trenston still has a user but Clerk is incomplete, only hard-logout if
 * Clerk is loaded and explicitly signed out (not pending / hydrating).
 */
export function shouldHardLogoutStaleTrenstonSession({
  clerkReady,
  user,
  clerkComplete,
  sessionStatus,
  isSignedIn,
  userId,
  sessionId,
  session,
}) {
  if (!clerkReady || !user || clerkComplete) return false;
  if (sessionStatus === "pending") return false;
  return isSignedIn === false && !userId && !sessionId && !session;
}
