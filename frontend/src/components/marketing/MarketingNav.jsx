import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion, useScroll, useSpring } from "motion/react";
import { ArrowRight, Menu, X } from "lucide-react";
import MarketingLogo from "@/components/marketing/MarketingLogo";
import { cn } from "@/lib/utils";
import { PUBLIC_CONTACT_MAILTO } from "@/lib/marketingCopy";

const NAV_LINKS = [
  { to: "/", label: "Home" },
  { to: "/features", label: "Features" },
  { to: "/integrations", label: "Integrations" },
  { to: "/pricing", label: "Pricing" },
  { to: "/security", label: "Security" },
  { to: "/about", label: "About" },
];

function isActive(path, active) {
  if (path === "/") return active === "/";
  return active === path || active?.startsWith(path);
}

/**
 * White editorial nav (black type, navy underline). A thin navy bar under the
 * header tracks reading progress. (Older call sites may still pass bgClassName; it is ignored.)
 */
export default function MarketingNav({ authed, onEnter, active }) {
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const { scrollYProgress } = useScroll();
  const progress = useSpring(scrollYProgress, { stiffness: 120, damping: 30, restDelta: 0.001 });

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={cn(
        "fixed inset-x-0 top-0 z-50 border-b bg-white transition-shadow duration-300",
        scrolled ? "border-mk-line shadow-[0_8px_30px_-18px_rgba(10,10,10,0.35)]" : "border-mk-line",
      )}
    >
      <div className="mx-auto max-w-7xl px-6">
        <div className="flex h-16 items-center justify-between gap-6">
          <MarketingLogo size="sm" />

          <nav className="hidden items-center gap-8 lg:flex" aria-label="Main">
            {NAV_LINKS.map((l) => {
              const on = isActive(l.to, active);
              return (
                <Link
                  key={l.to}
                  to={l.to}
                  aria-current={on ? "page" : undefined}
                  className={cn(
                    "mk-navlink text-[0.9375rem] transition-colors",
                    on ? "font-semibold text-mk-black" : "text-mk-gray hover:text-mk-black",
                  )}
                >
                  {l.label}
                </Link>
              );
            })}
          </nav>

          <div className="flex items-center gap-5">
            <a
              href={PUBLIC_CONTACT_MAILTO}
              data-testid="nav-contact-link"
              className="hidden text-sm text-mk-gray transition-colors hover:text-mk-black sm:inline"
            >
              Contact
            </a>
            {!authed && (
              <Link to="/login" className="hidden text-sm text-mk-gray transition-colors hover:text-mk-black sm:inline">
                Sign in
              </Link>
            )}
            <button
              data-testid="nav-signin-btn"
              type="button"
              onClick={onEnter}
              className="mk-btn mk-btn-dark mk-btn-sm hidden sm:inline-flex"
            >
              <span>{authed ? "Open cockpit" : "Get started"}</span>
              <ArrowRight className="mk-arrow h-3.5 w-3.5" aria-hidden />
            </button>
            <button
              type="button"
              className="p-1 text-mk-black lg:hidden"
              aria-label={open ? "Close menu" : "Open menu"}
              aria-expanded={open}
              onClick={() => setOpen((o) => !o)}
            >
              {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>
          </div>
        </div>
      </div>

      {open && (
        <nav className="border-t border-mk-line bg-white px-6 pb-6 pt-2 lg:hidden" aria-label="Mobile">
          {NAV_LINKS.map((l) => (
            <Link
              key={l.to}
              to={l.to}
              onClick={() => setOpen(false)}
              aria-current={isActive(l.to, active) ? "page" : undefined}
              className={cn(
                "flex items-center justify-between border-b border-mk-line py-4 text-lg",
                isActive(l.to, active) ? "font-semibold text-mk-black" : "text-mk-gray",
              )}
            >
              {l.label}
              <ArrowRight className="h-4 w-4" aria-hidden />
            </Link>
          ))}
          <div className="mt-5 flex flex-col gap-3">
            <a href={PUBLIC_CONTACT_MAILTO} onClick={() => setOpen(false)} className="text-sm text-mk-gray">
              Contact
            </a>
            {!authed && (
              <Link to="/login" onClick={() => setOpen(false)} className="text-sm text-mk-gray">
                Sign in
              </Link>
            )}
            <button
              type="button"
              onClick={() => { setOpen(false); onEnter?.(); }}
              className="mk-btn mk-btn-dark w-full"
            >
              <span>{authed ? "Open cockpit" : "Get started"}</span>
            </button>
          </div>
        </nav>
      )}

      <motion.div
        className="absolute inset-x-0 bottom-[-1px] h-[2px] origin-left bg-mk-navy"
        style={{ scaleX: progress }}
        aria-hidden
      />
    </header>
  );
}
