import { Link } from "react-router-dom";
import { PUBLIC_CONTACT_MAILTO } from "@/lib/marketingCopy";

const LINKS = [
  { to: "/", label: "Home" },
  { to: "/features", label: "Features" },
  { to: "/integrations", label: "Integrations" },
  { to: "/pricing", label: "Pricing" },
  { to: "/about", label: "About" },
  { to: "/security", label: "Security" },
];

/**
 * Compact top links for login / sign-up form column (light surface).
 * Brand mark lives centered above the auth headline — not duplicated here.
 */
export default function AuthMarketingHeader() {
  return (
    <header className="absolute top-0 inset-x-0 z-20 px-6 py-5 md:px-8">
      <nav className="flex flex-wrap items-center justify-between gap-3 text-sm text-helm-slate" aria-label="Marketing">
        <Link to="/" className="hover:text-helm-navy transition-colors whitespace-nowrap">
          ← Home
        </Link>
        <div className="hidden sm:flex flex-wrap items-center justify-end gap-x-4 gap-y-1">
          {LINKS.filter((l) => l.to !== "/").map((l) => (
            <Link key={l.to} to={l.to} className="hover:text-helm-navy transition-colors whitespace-nowrap">
              {l.label}
            </Link>
          ))}
          <a href={PUBLIC_CONTACT_MAILTO} className="hover:text-helm-navy transition-colors whitespace-nowrap">
            Contact
          </a>
        </div>
        <a href={PUBLIC_CONTACT_MAILTO} className="sm:hidden hover:text-helm-navy transition-colors">
          Contact
        </a>
      </nav>
    </header>
  );
}
