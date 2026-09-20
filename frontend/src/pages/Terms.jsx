import { Link } from "react-router-dom";
import { COMPANY_LOCATION, PUBLIC_CONTACT_EMAIL, PUBLIC_CONTACT_MAILTO } from "@/lib/marketingCopy";
import TrenstonMark from "@/components/HelmMark";

export default function Terms() {
  return (
    <div className="min-h-screen bg-helm-cream text-helm-navy">
      <div className="relative z-10 mx-auto max-w-3xl px-6 py-16 md:py-24">
        <Link to="/" className="inline-flex items-center gap-2 text-sm text-helm-slate hover:text-helm-navy transition-colors mb-10">
          <TrenstonMark size={24} className="rounded" />
          Back to Trenston
        </Link>

        <p className="font-mono text-xs uppercase tracking-[0.25em] text-helm-gold mb-4">Legal</p>
        <h1 className="font-display text-3xl md:text-4xl font-medium tracking-tight text-helm-navy">Terms of Service</h1>
        <p className="text-helm-slate text-sm mt-3">Last updated: September 3, 2026</p>

        <div className="mt-10 space-y-8 text-[15px] text-helm-navy/80 leading-relaxed">
          <section>
            <h2 className="text-lg text-helm-navy font-normal tracking-tight mb-2">Agreement</h2>
            <p>
              By accessing or using <span className="text-helm-navy">Trenston</span>, you agree to these Terms of Service with{" "}
              <span className="text-helm-navy">Trenston</span> (“we”, “us”), operated by{" "}
              <span className="text-helm-navy">Tansher Dhawan, Founder</span>. If you use Trenston on behalf of a company,
              you represent that you have authority to bind that company.
              Contact:{" "}
              <a href={PUBLIC_CONTACT_MAILTO} className="text-helm-gold hover:underline">{PUBLIC_CONTACT_EMAIL}</a>
              {" "}· {COMPANY_LOCATION}.
            </p>
          </section>

          <section>
            <h2 className="text-lg text-helm-navy font-normal tracking-tight mb-2">Eligibility</h2>
            <p>
              Trenston is open to individuals and businesses worldwide. There is no geographic restriction.
              Users under 18 should only use Trenston under a parent or guardian&apos;s supervision, at the guardian&apos;s
              discretion. Trenston does not independently verify age or guardian consent.
            </p>
          </section>

          <section>
            <h2 className="text-lg text-helm-navy font-normal tracking-tight mb-2">Account</h2>
            <p>
              You sign in through Clerk (including Google sign-in where available) and must keep your credentials secure.
              You are responsible for activity under your account and for ensuring workspace members have appropriate access.
            </p>
          </section>

          <section>
            <h2 className="text-lg text-helm-navy font-normal tracking-tight mb-2">Acceptable use</h2>
            <p>
              You may not misuse Trenston, attempt unauthorized access, disrupt the service, reverse engineer it except where
              permitted by law, or upload unlawful, infringing, or harmful content. You must only submit data you have the
              right to process, including when using AI features or connecting third-party integrations.
            </p>
          </section>

          <section className="rounded-lg border border-helm-line border-l-2 border-l-helm-gold/70 bg-helm-card p-5">
            <h2 className="text-lg text-helm-gold font-normal tracking-tight mb-2">AI accuracy: please read</h2>
            <p className="text-helm-fg">
              Trenston uses AI (Anthropic&apos;s Claude) to read uploaded documents and suggest financial entries, and to
              generate AI briefings and summaries. <span className="text-helm-navy font-medium">You must independently verify
              all AI-suggested data before relying on it for real business decisions.</span> Trenston and its creators are
              not liable for financial or operational decisions made based on unverified AI output. AI features are
              assistive tools, not legal, financial, tax, or other professional advice.
            </p>
          </section>

          <section>
            <h2 className="text-lg text-helm-navy font-normal tracking-tight mb-2">Subscriptions &amp; billing</h2>
            <p>
              Paid plans are billed by <span className="text-helm-navy">Paddle</span> as merchant of record. Current plan
              options, prices, and feature limits are shown on the{" "}
              <Link to="/app/billing" className="text-helm-gold hover:underline">Billing</Link> page (and marketing pricing).
              Paid plans include a <span className="text-helm-navy">7-day free trial</span>. After a payment is processed,
              charges are non-refundable. See our{" "}
              <Link to="/refunds" className="text-helm-gold hover:underline">Refund &amp; Billing Policy</Link>.
              You may cancel anytime; cancellation takes effect at the end of the current billing period.
              Failure to pay may result in downgrade or suspension of paid features.
            </p>
          </section>

          <section>
            <h2 className="text-lg text-helm-navy font-normal tracking-tight mb-2">Integrations</h2>
            <p>
              Optional integrations (such as Google Calendar, QuickBooks, Xero, SAP Business One, or HubSpot) only access data after you explicitly connect
              them. Your use of those services remains subject to their own terms and privacy policies.
            </p>
          </section>

          <section>
            <h2 className="text-lg text-helm-navy font-normal tracking-tight mb-2">Limitation of liability</h2>
            <p>
              To the fullest extent permitted by law, Trenston and its suppliers are not liable for indirect,
              incidental, special, consequential, or punitive damages, or for lost profits, data, or business
              opportunities arising from your use of Trenston.{" "}
              <span className="text-helm-navy">Our total liability to you for any claim relating to the service is capped
              at the total amount you have paid Trenston in membership fees.</span>{" "}
              If you have not paid for Trenston, that amount is zero.
            </p>
          </section>

          <section>
            <h2 className="text-lg text-helm-navy font-normal tracking-tight mb-2">Account suspension &amp; termination</h2>
            <p>
              You may stop using Trenston and delete your account at any time from{" "}
              <Link to="/app/settings" className="text-helm-gold hover:underline">Account Settings</Link>.
              Account deletion wipes your data immediately.
              We reserve the right to suspend or terminate accounts for abuse, non-payment, or violation of these Terms
              of Service, or as required by law. Provisions that by nature should survive (including disclaimers and
              liability limits) will survive termination.
            </p>
          </section>

          <section>
            <h2 className="text-lg text-helm-navy font-normal tracking-tight mb-2">Governing law</h2>
            <p>
              These Terms are governed by the laws of the Philippines. This may change once the business entity is
              formally registered in another jurisdiction.
            </p>
          </section>

          <section>
            <h2 className="text-lg text-helm-navy font-normal tracking-tight mb-2">Privacy</h2>
            <p>
              How we handle personal and business data is described in our{" "}
              <Link to="/privacy" className="text-helm-gold hover:underline">Privacy Policy</Link>.
              Current product security practices are described on the{" "}
              <Link to="/security" className="text-helm-gold hover:underline">Security</Link> page.
            </p>
          </section>

          <section>
            <h2 className="text-lg text-helm-navy font-normal tracking-tight mb-2">Contact</h2>
            <p>
              Questions about these Terms:{" "}
              <a href={PUBLIC_CONTACT_MAILTO} className="text-helm-gold hover:underline">{PUBLIC_CONTACT_EMAIL}</a>
              {" "}· Trenston · {COMPANY_LOCATION}.
            </p>
          </section>
        </div>

        <p className="mt-12 text-xs text-helm-slate border-t border-helm-navy/5 pt-6">
          This policy will be reviewed by legal counsel as Trenston grows; contact us with questions.
        </p>
      </div>
    </div>
  );
}
