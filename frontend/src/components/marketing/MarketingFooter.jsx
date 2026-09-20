import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight } from "lucide-react";
import MarketingLogo from "@/components/marketing/MarketingLogo";
import {
  CATEGORY,
  COMPANY_LOCATION,
  PUBLIC_CONTACT_EMAIL,
  PUBLIC_CONTACT_MAILTO,
  PUBLIC_INSTAGRAM_HANDLE,
  PUBLIC_INSTAGRAM_URL,
} from "@/lib/marketingCopy";

const PRIMARY_NAV = [
  { to: "/features", label: "Features" },
  { to: "/pricing", label: "Pricing" },
  { to: "/integrations", label: "Integrations" },
  { to: "/about", label: "About" },
  { to: "/help", label: "Help" },
  { href: PUBLIC_CONTACT_MAILTO, label: "Contact" },
];

const UTILITY_LINKS = [
  { to: "/privacy", label: "Privacy" },
  { to: "/terms", label: "Terms" },
  { to: "/refunds", label: "Refunds" },
  { to: "/security", label: "Security" },
  { to: "/status", label: "Status" },
  { to: "/changelog", label: "Changelog" },
  { to: "/login", label: "Sign in" },
  { to: "/sign-up", label: "Create account" },
];

function formatManilaTime(date) {
  return date.toLocaleTimeString("en-PH", {
    timeZone: "Asia/Manila",
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
    hour12: true,
  });
}

function ManilaClock() {
  const [now, setNow] = useState(() => formatManilaTime(new Date()));

  useEffect(() => {
    const tick = () => setNow(formatManilaTime(new Date()));
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, []);

  return (
    <time
      dateTime={new Date().toISOString()}
      data-testid="footer-manila-clock"
      title="Asia/Manila"
      className="font-mono tabular-nums text-helm-slate"
    >
      {now} · Manila
    </time>
  );
}

function ExternalHint() {
  return <ArrowUpRight className="inline-block h-3 w-3 shrink-0 opacity-70" aria-hidden />;
}

export default function MarketingFooter() {
  const year = new Date().getFullYear();

  return (
    <footer className="relative overflow-hidden border-t border-helm-cream/10 bg-helm-ink px-6 pt-14 pb-10">
      <div className="relative z-10 mx-auto max-w-6xl flex flex-col gap-12">
        <div className="grid grid-cols-1 gap-10 md:grid-cols-12 md:gap-8">
          {/* Brand + contact */}
          <div className="md:col-span-4 flex flex-col gap-4">
            <MarketingLogo size="sm" showTagline dark />
            <p className="text-sm text-helm-slate max-w-xs leading-relaxed">
              The {CATEGORY.toLowerCase()} for founders and owners running real operations — however lean the team. One cockpit. Clear decisions. Quiet control.
            </p>
            <div className="mt-1">
              <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-helm-slate/80">Contact</p>
              <a
                href={PUBLIC_CONTACT_MAILTO}
                data-testid="footer-contact-link"
                className="mt-2 block text-sm text-helm-cream/85 hover:text-helm-cream transition-colors"
              >
                {PUBLIC_CONTACT_EMAIL}
              </a>
              <p className="mt-1 text-sm text-helm-slate">{COMPANY_LOCATION}</p>
            </div>
          </div>

          {/* Primary navigation — visual anchor */}
          <nav className="md:col-span-4" aria-label="Footer navigation">
            <ul className="flex flex-col gap-1.5 sm:gap-2">
              {PRIMARY_NAV.map((l) => (
                <li key={l.label}>
                  {l.href ? (
                    <a
                      href={l.href}
                      data-testid="footer-contact-cta"
                      className="font-display text-2xl sm:text-3xl md:text-[2rem] font-semibold tracking-tight text-helm-cream hover:text-helm-gold transition-colors leading-tight"
                    >
                      {l.label}
                    </a>
                  ) : (
                    <Link
                      to={l.to}
                      className="font-display text-2xl sm:text-3xl md:text-[2rem] font-semibold tracking-tight text-helm-cream hover:text-helm-gold transition-colors leading-tight"
                    >
                      {l.label}
                    </Link>
                  )}
                </li>
              ))}
            </ul>
          </nav>

          {/* Connect */}
          <div className="md:col-span-4 md:pl-4">
            <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-helm-slate">Connect</p>
            <ul className="mt-3 flex flex-col gap-2.5 text-sm text-helm-slate">
              <li>
                <a
                  href={PUBLIC_INSTAGRAM_URL}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 hover:text-helm-cream transition-colors"
                >
                  <span>Instagram {PUBLIC_INSTAGRAM_HANDLE}</span>
                  <ExternalHint />
                </a>
              </li>
              <li>
                <a
                  href={PUBLIC_CONTACT_MAILTO}
                  className="inline-flex items-center gap-1.5 hover:text-helm-cream transition-colors"
                >
                  <span>{PUBLIC_CONTACT_EMAIL}</span>
                  <ExternalHint />
                </a>
              </li>
            </ul>
          </div>
        </div>

        {/* Secondary utility / legal / auth */}
        <nav
          className="flex flex-wrap gap-x-5 gap-y-2 text-xs text-helm-slate"
          aria-label="Footer utility"
        >
          {UTILITY_LINKS.map((l) => (
            <Link
              key={l.to}
              to={l.to}
              className="hover:text-helm-cream/80 transition-colors font-normal"
            >
              {l.label}
            </Link>
          ))}
        </nav>

        {/* Bottom bar */}
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-t border-helm-cream/10 pt-6 text-[11px] text-helm-slate">
          <p>© {year} Trenston</p>
          <Link to="/privacy" className="hover:text-helm-cream/80 transition-colors">
            Legal
          </Link>
          <ManilaClock />
        </div>
      </div>

      {/* Faint brand watermark — bleeds past the bottom edge */}
      <p
        aria-hidden
        className="pointer-events-none absolute inset-x-0 -bottom-[0.18em] z-0 select-none text-center font-display font-semibold leading-none tracking-[-0.04em] text-[clamp(4.5rem,22vw,14rem)] text-helm-cream/[0.045]"
      >
        TRENSTON
      </p>
    </footer>
  );
}
