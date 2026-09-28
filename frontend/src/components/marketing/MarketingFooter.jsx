import { Link } from "react-router-dom";
import { ArrowUpRight, Instagram } from "lucide-react";
import FounderCredit from "@/components/marketing/FounderCredit";
import MarketingLogo from "@/components/marketing/MarketingLogo";
import trenstonWordmarkWhite from "@/assets/trenston-wordmark-white.svg";
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

const linkClass = "mk-link !font-normal text-sm text-mk-gray-dark hover:text-white transition-colors";

function FooterLink({ item }) {
  const inner = <span>{item.label}</span>;
  if (item.href) {
    return (
      <a href={item.href} data-testid={item.testId} className={linkClass}>
        {inner}
      </a>
    );
  }
  return (
    <Link to={item.to} data-testid={item.testId} className={linkClass}>
      {inner}
    </Link>
  );
}

export default function MarketingFooter() {
  const year = new Date().getFullYear();

  return (
    <footer className="relative overflow-hidden bg-mk-black text-white">
      <div className="mx-auto max-w-7xl px-6 pt-20">
        <div className="grid gap-14 border-b border-white/15 pb-16 lg:grid-cols-[1.2fr_1fr]">
          <div className="max-w-md">
            <MarketingLogo variant="lockup" dark size="sm" />
            <p className="mt-6 text-xs font-semibold uppercase tracking-[0.18em] text-mk-gray-dark">{CATEGORY}</p>
            <h2 className="mt-4 text-4xl font-semibold leading-[1.02] tracking-[-0.035em] md:text-5xl">
              Run a tighter company.
            </h2>
            <a
              href={PUBLIC_CONTACT_MAILTO}
              data-testid="footer-contact-link"
              className="group mt-8 inline-flex items-center gap-2 border-b border-white/30 pb-1 text-lg transition-colors hover:border-white"
            >
              {PUBLIC_CONTACT_EMAIL}
              <ArrowUpRight className="h-4 w-4 transition-transform duration-300 group-hover:-translate-y-0.5 group-hover:translate-x-0.5" aria-hidden />
            </a>
            <p className="mt-3 text-sm text-mk-gray-dark">{COMPANY_LOCATION}</p>
          </div>

          <nav className="grid grid-cols-2 gap-10 sm:grid-cols-3" aria-label="Footer navigation">
            {Object.entries(FOOTER_LINKS).map(([group, links]) => (
              <div key={group}>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-white">{group}</p>
                <ul className="mt-5 flex flex-col gap-3">
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

        <div className="flex flex-col gap-4 py-8 text-xs text-mk-gray-dark sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-5">
            <p>BGC, Manila</p>
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
          </div>
          <p>© {year} Trenston. All rights reserved.</p>
        </div>
      </div>

      <div className="border-t border-white/10 px-6 pb-8 pt-10">
        <img
          src={trenstonWordmarkWhite}
          alt=""
          aria-hidden
          className="mx-auto w-full max-w-7xl select-none opacity-95"
          draggable={false}
        />
      </div>
    </footer>
  );
}
