// Loads Paddle.js v2 once. Initialize at most once; keep the event callback fresh
// for SPA re-checkouts in the same tab (Paddle only supports Initialize once).
let loaded;
let initialized = false;
let latestOnEvent = null;

export function loadPaddle() {
  if (window.Paddle) return Promise.resolve(window.Paddle);
  if (loaded) return loaded;
  loaded = new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = "https://cdn.paddle.com/paddle/v2/paddle.js";
    s.async = true;
    s.onload = () => resolve(window.Paddle);
    s.onerror = () => reject(new Error("Unable to load Paddle.js"));
    document.head.appendChild(s);
  });
  return loaded;
}

export async function initPaddle(token, environment, onEvent, paddleCustomerId) {
  const P = await loadPaddle();
  latestOnEvent = onEvent || null;
  if (!initialized) {
    if (environment === "sandbox") {
      P.Environment.set("sandbox");
    }
    const opts = {
      token,
      eventCallback: (event) => {
        if (typeof latestOnEvent === "function") latestOnEvent(event);
      },
    };
    // Retain needs Paddle's customer id (ctm_…), not our workspace id.
    if (typeof paddleCustomerId === "string" && paddleCustomerId.startsWith("ctm_")) {
      opts.pwCustomer = { id: paddleCustomerId };
    }
    P.Initialize(opts);
    initialized = true;
  }
  return P;
}
