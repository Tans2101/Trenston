import { Link } from "react-router-dom";
import { Instagram } from "lucide-react";
import FounderCredit from "@/components/marketing/FounderCredit";
import MarketingLogo from "@/components/marketing/MarketingLogo";
import trenstonWordmarkWhiteOnInk from "@/assets/trenston-wordmark-white-on-ink.svg";
import trenstonWordmarkBlack from "@/assets/trenston-wordmark-black.svg";
import {
  CATEGORY,
  COMPANY_LOCATION,
  PUBLIC_CONTACT_EMAIL,
  PUBLIC_CONTACT_MAILTO,
  PUBLIC_INSTAGRAM_HANDLE,
  PUBLIC_INSTAGRAM_URL,
} from "@/lib/marketingCopy";

const FOOTER_LINKS = {
  Product: [
    { to: "/features", label: "Features" },
    { to: "/integrations", label: "Integrations" },
    { to: "/pricing", label: "Pricing" },
    { to: "/changelog", label: "Changelog" },
    { to: "/status", label: "Status" },
  ],
  Company: [
    { to: "/about", label: "About" },
    { href: PUBLIC_CONTACT_MAILTO, label: "Contact", testId: "footer-contact-cta" },
    { to: "/login", label: "Sign in" },
    { to: "/sign-up", label: "Create account" },
  ],
  Support: [
    { to: "/help", label: "Help" },
    { to: "/security", label: "Security" },
    { to: "/privacy", label: "Privacy" },
    { to: "/terms", label: "Terms" },
    { to: "/refunds", label: "Refunds" },
  ],
};

const linkClass =
  "text-sm text-helm-cream hover:opacity-60 transition-opacity";

function FooterLink({ item }) {
  if (item.href) {
    return (
      <a href={item.href} data-testid={item.testId} className={linkClass}>
        {item.label}
      </a>
    );
  }
  return (
    <Link to={item.to} data-testid={item.testId} className={linkClass}>
      {item.label}
    </Link>
  );
}

export default function MarketingFooter() {
  const year = new Date().getFullYear();

  return (
    <footer className="relative overflow-hidden bg-helm-ink">
      <div className="relative z-10 mx-auto max-w-6xl px-6 md:px-10 pt-12 md:pt-16 flex flex-col gap-12 md:gap-14">
        {/* Top: brand column + link columns */}
        <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-10">
          <div className="max-w-xs flex flex-col gap-4">
            <MarketingLogo variant="lockup" dark size="sm" />
            <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-helm-cream/70">
              {CATEGORY}
            </p>
            <h2 className="font-display text-2xl md:text-3xl text-helm-cream tracking-tight">
              Run a tighter company.
            </h2>
          </div>
          <nav
            className="grid grid-cols-2 sm:grid-cols-3 gap-8 md:gap-12"
            aria-label="Footer navigation"
          >
            {Object.entries(FOOTER_LINKS).map(([group, links]) => (
              <div key={group}>
                <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-helm-cream/70">
                  {group}
                </p>
                <ul className="mt-3 flex flex-col gap-2">
                  {links.map((item) => (
                    <li key={item.label}>
                      <FooterLink item={item} />
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </nav>
        </div>

        {/* Middle: contact card + Instagram */}
        <div className="flex flex-col sm:flex-row sm:items-stretch gap-4 sm:gap-6">
          <div className="flex-1 border border-helm-cream/25 px-5 py-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div>
              <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-helm-cream/70">
                Contact
              </p>
              <a
                href={PUBLIC_CONTACT_MAILTO}
                data-testid="footer-contact-link"
                className="mt-2 block text-sm text-helm-cream hover:opacity-60 transition-opacity"
              >
                {PUBLIC_CONTACT_EMAIL}
              </a>
              <p className="mt-1 text-sm text-helm-cream/80">{COMPANY_LOCATION}</p>
            </div>
            <a
              href={PUBLIC_CONTACT_MAILTO}
              className="inline-flex items-center justify-center rounded-md bg-helm-cream text-helm-navy text-sm font-medium px-4 py-2.5 hover:opacity-90 transition-opacity shrink-0"
            >
              Contact Us
            </a>
          </div>
          <a
            href={PUBLIC_INSTAGRAM_URL}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={`Trenston on Instagram ${PUBLIC_INSTAGRAM_HANDLE}`}
            className="inline-flex items-center justify-center gap-2 border border-helm-cream/25 px-5 py-4 text-helm-cream hover:opacity-60 transition-opacity sm:w-auto"
          >
            <Instagram className="h-5 w-5" aria-hidden />
            <span className="text-sm font-medium">{PUBLIC_INSTAGRAM_HANDLE}</span>
          </a>
        </div>

        {/* Bottom meta */}
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between font-mono text-[11px] text-helm-cream/80 pb-10 md:pb-12">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-4">
            <p>🇵🇭 BGC, Manila</p>
            <FounderCredit
              data-testid="footer-founder-credit"
              creditClassName="text-helm-cream/80"
              linkClassName="text-helm-cream/80 hover:text-helm-cream"
            />
          </div>
          <p>© {year} Trenston. All rights reserved.</p>
        </div>

        {/* White-on-ink signature on the near-black footer field */}
        <div className="relative z-0 -mx-6 md:-mx-10 px-6 md:px-10 pb-6 md:pb-8" aria-hidden>
          <img
            src={trenstonWordmarkWhiteOnInk}
            alt=""
            className="w-full max-w-3xl opacity-90 select-none pointer-events-none"
            draggable={false}
          />
        </div>
      </div>

      {/* Ember pop band — black wordmark for contrast on orange */}
      <div className="relative z-10 bg-helm-ember px-6 md:px-10 py-8 md:py-10 overflow-hidden">
        <img
          src={trenstonWordmarkBlack}
          alt=""
          aria-hidden
          className="mx-auto w-full max-w-4xl select-none pointer-events-none"
          draggable={false}
        />
      </div>
    </footer>
  );
}
