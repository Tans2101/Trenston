import { useState, useEffect } from "react";
import { Link } from "react-router-dom";

const KEY = "helm_cookie_ok";

export default function CookieNotice() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    try {
      if (!localStorage.getItem(KEY)) setVisible(true);
    } catch {
      setVisible(true);
    }
  }, []);

  const dismiss = () => {
    try {
      localStorage.setItem(KEY, "1");
    } catch { /* ignore */ }
    setVisible(false);
  };

  if (!visible) return null;

  return (
    <div
      data-testid="cookie-notice"
      className="fixed bottom-0 inset-x-0 z-[100] p-4 md:p-5"
    >
      <div className="mx-auto max-w-3xl flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-4 rounded-[2px] border border-helm-line bg-helm-card px-4 py-3.5 shadow-2xl">
        <p className="flex-1 text-sm text-helm-fg leading-relaxed">
          Trenston uses a session cookie to keep you signed in, a small preference to remember this notice,
          and cookieless Vercel Analytics for page views. No advertising cookies. Details in our{" "}
          <Link to="/privacy" className="font-semibold text-helm-fg underline underline-offset-2 hover:opacity-80">Privacy Policy</Link>.
        </p>
        <button
          data-testid="cookie-accept-btn"
          onClick={dismiss}
          className="shrink-0 rounded-[2px] bg-white text-[#0a0a0a] text-sm font-semibold px-4 py-2 transition-colors hover:bg-[#9db5e3]"
        >
          Got it
        </button>
      </div>
    </div>
  );
}
