import { Link } from "react-router-dom";
import { Instagram, Mail } from "lucide-react";
import MarketingLogo from "@/components/marketing/MarketingLogo";
import {
  CATEGORY,
  PUBLIC_CONTACT_EMAIL,
  PUBLIC_CONTACT_MAILTO,
  PUBLIC_INSTAGRAM_HANDLE,
  PUBLIC_INSTAGRAM_URL,
  TAGLINE,
} from "@/lib/marketingCopy";

const FOOTER_LINKS = [
  { to: "/", label: "Home" },
  { to: "/features", label: "Features" },
  { to: "/integrations", label: "Integrations" },
  { to: "/pricing", label: "Pricing" },
  { to: "/about", label: "About" },
  { href: PUBLIC_CONTACT_MAILTO, label: "Contact" },
  { to: "/help", label: "Help" },
  { to: "/security", label: "Security" },
  { to: "/changelog", label: "Changelog" },
  { to: "/status", label: "Status" },
  { to: "/login", label: "Sign in" },
  { to: "/sign-up", label: "Create account" },
  { to: "/privacy", label: "Privacy" },
  { to: "/terms", label: "Terms" },
  { to: "/refunds", label: "Refunds" },
];

export default function MarketingFooter() {
  const year = new Date().getFullYear();

  return (
    <footer className="px-6 py-12 border-t border-helm-cream/10 bg-helm-ink">
      <div className="mx-auto max-w-6xl flex flex-col gap-10">
        <div className="rounded-lg border border-helm-cream/10 bg-helm-ink-card px-6 py-6 md:px-8 md:py-7 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-helm-slate">Contact us</p>
            <p className="mt-2 text-sm text-helm-cream/85 leading-relaxed max-w-md">
              Questions about Trenston, security, or billing? Email us — we read every message.
            </p>
          </div>
          <a
            href={PUBLIC_CONTACT_MAILTO}
            data-testid="footer-contact-cta"
            className="inline-flex items-center justify-center gap-2 rounded-md bg-helm-cream text-helm-navy text-sm font-medium px-5 py-2.5 transition-colors hover:bg-helm-gold shrink-0"
          >
            <Mail className="h-4 w-4" aria-hidden />
            {PUBLIC_CONTACT_EMAIL}
          </a>
        </div>

        <p className="text-center text-sm text-helm-slate max-w-md mx-auto leading-relaxed">{TAGLINE}</p>

        <div className="flex flex-col md:flex-row md:items-start justify-between gap-8">
          <div className="flex flex-col gap-2">
            <MarketingLogo size="sm" showTagline dark />
            <p className="text-xs text-helm-slate max-w-xs leading-relaxed mt-1">
              The {CATEGORY.toLowerCase()} for founders and owners running real operations — however lean the team. One cockpit. Clear decisions. Quiet control.
            </p>
            <a
              href={PUBLIC_INSTAGRAM_URL}
              target="_blank"
              rel="noopener noreferrer"
              aria-label={`Instagram ${PUBLIC_INSTAGRAM_HANDLE}`}
              title={`Instagram ${PUBLIC_INSTAGRAM_HANDLE}`}
              className="mt-2 inline-flex w-fit text-helm-slate hover:text-helm-cream transition-colors"
            >
              <Instagram className="h-4 w-4" aria-hidden />
            </a>
          </div>
          <nav className="grid grid-cols-2 sm:grid-cols-4 gap-x-8 gap-y-3 text-sm text-helm-slate" aria-label="Footer">
            {FOOTER_LINKS.map((l) => (
              l.href ? (
                <a
                  key={l.href + l.label}
                  href={l.href}
                  data-testid="footer-contact-link"
                  className="hover:text-helm-cream transition-colors"
                >
                  {l.label}
                </a>
              ) : (
                <Link key={l.to + l.label} to={l.to} className="hover:text-helm-cream transition-colors">
                  {l.label}
                </Link>
              )
            ))}
          </nav>
        </div>

        <p className="text-center text-[11px] text-helm-slate">
          © {year} Trenston
        </p>
      </div>
    </footer>
  );
}
