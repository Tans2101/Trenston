import { Link } from "react-router-dom";
import { ArrowUpRight, Instagram } from "lucide-react";
import FounderCredit from "@/components/marketing/FounderCredit";
import MarketingLogo from "@/components/marketing/MarketingLogo";
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

const linkClass = "text-sm text-mk-gray-dark transition-colors hover:text-white hover:underline underline-offset-4";

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

/** Four-column black footer with a plain legal bar — BlackRock-style. */
export default function MarketingFooter() {
  const year = new Date().getFullYear();

  return (
    <footer className="bg-mk-black text-white">
      <div className="mx-auto max-w-7xl px-6">
        <div className="grid gap-12 border-b border-white/15 py-16 md:grid-cols-2 lg:grid-cols-[1.4fr_1fr_1fr_1fr]">
          <div className="max-w-sm">
            <MarketingLogo variant="lockup" dark size="sm" />
            <p className="mt-6 text-xs font-semibold uppercase tracking-[0.16em] text-mk-gray-dark">{CATEGORY}</p>
            <p className="mt-3 text-2xl font-medium tracking-[-0.02em]">Run a tighter company.</p>
            <a
              href={PUBLIC_CONTACT_MAILTO}
              data-testid="footer-contact-link"
              className="group mt-6 inline-flex items-center gap-1.5 text-sm text-white transition-colors hover:underline hover:underline-offset-4"
            >
              {PUBLIC_CONTACT_EMAIL}
              <ArrowUpRight className="h-4 w-4 transition-transform duration-300 group-hover:-translate-y-0.5 group-hover:translate-x-0.5" aria-hidden />
            </a>
            <p className="mt-2 text-sm text-mk-gray-dark">{COMPANY_LOCATION}</p>
          </div>

          {Object.entries(FOOTER_LINKS).map(([group, links]) => (
            <nav key={group} aria-label={`${group} links`}>
              <p className="text-sm font-semibold text-white">{group}</p>
              <ul className="mt-5 flex flex-col gap-3">
                {links.map((item) => (
                  <li key={item.label}>
                    <FooterLink item={item} />
                  </li>
                ))}
              </ul>
            </nav>
          ))}
        </div>

        <div className="flex flex-col gap-4 py-8 text-xs text-mk-gray-dark md:flex-row md:items-center md:justify-between">
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
            <FounderCredit
              data-testid="footer-founder-credit"
              creditClassName="text-mk-gray-dark"
              linkClassName="text-mk-gray-dark hover:text-white"
            />
            <a
              href={PUBLIC_INSTAGRAM_URL}
              target="_blank"
              rel="noopener noreferrer"
              aria-label={`Trenston on Instagram ${PUBLIC_INSTAGRAM_HANDLE}`}
              className="inline-flex items-center gap-1.5 transition-colors hover:text-white"
            >
              <Instagram className="h-4 w-4" aria-hidden />
              {PUBLIC_INSTAGRAM_HANDLE}
            </a>
            <Link to="/privacy" className="transition-colors hover:text-white">Privacy</Link>
            <Link to="/terms" className="transition-colors hover:text-white">Terms</Link>
          </div>
          <p>© {year} Trenston. All rights reserved.</p>
        </div>
      </div>
    </footer>
  );
}
