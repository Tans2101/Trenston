import { useState, useEffect, useRef } from "react";
import { Link } from "react-router-dom";

const KEY = "helm_cookie_ok";

export default function CookieNotice() {
  const [visible, setVisible] = useState(false);
  const [reserve, setReserve] = useState(0);
  const ref = useRef(null);

  useEffect(() => {
    try {
      if (!localStorage.getItem(KEY)) setVisible(true);
    } catch {
      setVisible(true);
    }
  }, []);

  // Reserve room at the end of the page while the notice is up, so bottom buttons can scroll
  // clear of it. A spacer in normal flow works even though html/body/#root are height: 100%.
  useEffect(() => {
    const el = ref.current;
    if (!visible || !el) return undefined;
    const measure = () => setReserve(el.offsetHeight);
    measure();
    const observer = typeof ResizeObserver !== "undefined" ? new ResizeObserver(measure) : null;
    observer?.observe(el);
    return () => observer?.disconnect();
  }, [visible]);

  const dismiss = () => {
    try {
      localStorage.setItem(KEY, "1");
    } catch { /* ignore */ }
    setVisible(false);
  };

  if (!visible) return null;

  return (
    <>
      <div aria-hidden="true" style={{ height: reserve }} />
      <div
        ref={ref}
        data-testid="cookie-notice"
        className="fixed bottom-0 inset-x-0 z-[100] p-4 md:p-5 pointer-events-none"
      >
        <div className="pointer-events-auto mx-auto max-w-3xl flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-4 rounded-[2px] border border-helm-line bg-helm-card px-4 py-3.5 shadow-2xl">
          <p className="flex-1 text-sm text-helm-fg leading-relaxed">
            Trenston uses a session cookie to keep you signed in, a small preference to remember this notice,
            and cookieless Vercel Analytics for page views. No advertising cookies. Details in our{" "}
            <Link to="/privacy" className="font-semibold text-helm-fg underline underline-offset-2 hover:opacity-80">Privacy Policy</Link>.
          </p>
          <button
            type="button"
            data-testid="cookie-accept-btn"
            onClick={dismiss}
            className="shrink-0 rounded-md bg-helm-gold text-helm-navy text-sm font-medium px-4 py-2 transition-colors hover:bg-helm-gold-hover"
          >
            Got it
          </button>
        </div>
      </div>
    </>
  );
}
