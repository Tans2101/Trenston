/**
 * Keeps an in-progress "Connect an AI assistant" sign-in alive across the login
 * page: when a signed-out person lands on /app/oauth/authorize, remember the full
 * URL, and send them back to it once they are signed in.
 */
const KEY = "trenston_oauth_return";
const PREFIX = "/app/oauth/authorize";

export function rememberOAuthReturn(location) {
  try {
    if (location?.pathname?.startsWith(PREFIX)) {
      sessionStorage.setItem(KEY, `${location.pathname}${location.search || ""}`);
    }
  } catch {
    /* storage unavailable: the person can restart the connection from the assistant */
  }
}

export function takeOAuthReturn() {
  try {
    const value = sessionStorage.getItem(KEY);
    sessionStorage.removeItem(KEY);
    return value && value.startsWith(PREFIX) ? value : null;
  } catch {
    return null;
  }
}
