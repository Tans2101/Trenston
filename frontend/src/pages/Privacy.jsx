import { Link } from "react-router-dom";
import { COMPANY_LOCATION, PUBLIC_CONTACT_EMAIL, PUBLIC_CONTACT_MAILTO } from "@/lib/marketingCopy";
import TrenstonMark from "@/components/HelmMark";

export default function Privacy() {
  return (
    <div className="min-h-screen bg-white text-mk-black">
      <div className="relative z-10 mx-auto max-w-3xl px-6 py-16 md:py-24">
        <Link to="/" className="inline-flex items-center gap-2 text-sm text-mk-gray hover:text-mk-black transition-colors mb-10">
          <TrenstonMark size={24} className="rounded" />
          Back to Trenston
        </Link>

        <p className="font-mono text-xs uppercase tracking-[0.25em] text-mk-navy mb-4">Legal</p>
        <h1 className="font-display text-3xl md:text-4xl font-medium tracking-tight text-mk-black">Privacy Policy</h1>
        <p className="text-mk-gray text-sm mt-3">Last updated: September 24, 2026</p>

        <div className="mt-10 space-y-8 text-[15px] text-mk-black/80 leading-relaxed">
          <section>
            <h2 className="text-lg text-mk-black font-normal tracking-tight mb-2">Who we are</h2>
            <p>
              This Privacy Policy explains how <span className="text-mk-black">Trenston</span> (“we”, “us”),
              operated by <span className="text-mk-black">Tansher Dhawan, Founder</span>,
              collects and uses information when you use <span className="text-mk-black">Trenston</span>, our company cockpit product.
              Contact:{" "}
              <a href={PUBLIC_CONTACT_MAILTO} className="text-mk-navy hover:underline">{PUBLIC_CONTACT_EMAIL}</a>.
              Postal address: {COMPANY_LOCATION}.
            </p>
          </section>

          <section>
            <h2 className="text-lg text-mk-black font-normal tracking-tight mb-2">Who can use Trenston</h2>
            <p>
              Trenston is open to individuals and businesses worldwide. There is no geographic restriction.
              Before creating a company workspace, you must confirm that you are 18 or older, or that you are using
              Trenston under a parent or guardian&apos;s supervision. Trenston records that confirmation on your account.
              We do not independently verify age or guardian consent beyond that acknowledgment.
            </p>
          </section>

          <section>
            <h2 className="text-lg text-mk-black font-normal tracking-tight mb-2">Account &amp; profile data</h2>
            <p>
              When you sign up, we collect your name, email address, and company information needed to create your
              workspace. Authentication is handled by <span className="text-mk-black">Clerk</span>; we receive basic
              identity details (such as name, email, and profile picture when provided) to create and secure your session.
              We do not ask for additional personal profile fields beyond what is required to run your account.
            </p>
          </section>

          <section>
            <h2 className="text-lg text-mk-black font-normal tracking-tight mb-2">Financial &amp; business data</h2>
            <p>
              Trenston stores the business data you enter or generate in the product, for example revenue and expense entries,
              categories, tasks, decisions, reports, team roster, pipeline deals, and related workspace content.
              Financial figures come from what you manually enter, from documents you upload, or from accounting systems
              you explicitly connect (QuickBooks, Xero, or SAP Business One). Pipeline deal records may also come from
              HubSpot when you connect it.
            </p>
          </section>

          <section>
            <h2 className="text-lg text-mk-black font-normal tracking-tight mb-2">Uploaded documents</h2>
            <p>
              Documents you upload (such as bills, receipts, or invoices) are stored in a private{" "}
              <span className="text-mk-black">Cloudflare R2</span> bucket. Files are not publicly accessible.
              When you upload a document for extraction, it is sent to <span className="text-mk-black">Anthropic&apos;s Claude API</span>{" "}
              for automated parsing. <span className="text-mk-black">No human at Trenston views your uploaded documents</span>,
              only the automated Claude process does, solely to extract suggested entries for your workspace.
            </p>
          </section>

          <section>
            <h2 className="text-lg text-mk-black font-normal tracking-tight mb-2">Google data</h2>
            <p>
              If you connect Google from Integrations, Trenston requests access to{" "}
              <span className="text-mk-black">Google Calendar</span> (read events, and write events when you
              create or update them in Trenston), <span className="text-mk-black">Gmail</span> (read message
              metadata and short snippets for the briefing; compose access to create drafts. Trenston does not
              send mail), <span className="text-mk-black">Google Sheets</span> (create a Financials export
              spreadsheet you trigger), and <span className="text-mk-black">Google Drive</span> files you
              pick in Trenston (bill import via <span className="font-mono text-xs">drive.file</span>, not full Drive).
              For Gmail we do not store full email bodies as a mailbox archive, only the metadata needed to
              render the current briefing. Trenston does not request <span className="font-mono text-xs">gmail.send</span>.
              Each teammate connects their own Google account; Trenston never surfaces another person&apos;s Google
              Calendar or Gmail to you. Nothing from Google is accessed until you explicitly connect.
              Company-shared OAuth grants (QuickBooks, Xero, HubSpot, SAP) may only be used by the teammate who
              connected them, or by a workspace owner.
            </p>
          </section>

          <section>
            <h2 className="text-lg text-mk-black font-normal tracking-tight mb-2">CRM data (HubSpot)</h2>
            <p>
              HubSpot CRM data is pulled only if and when you explicitly connect HubSpot via Integrations.
              We sync deal metadata (name, associated company name, value, stage, and close date) into your workspace
              Pipeline. OAuth tokens for HubSpot are encrypted at rest. Nothing is accessed before that connection.
            </p>
          </section>

          <section>
            <h2 className="text-lg text-mk-black font-normal tracking-tight mb-2">QuickBooks &amp; Xero data</h2>
            <p>
              QuickBooks (Intuit) or Xero accounting data is pulled only if and when you explicitly connect that account via
              Integrations. From QuickBooks we sync invoices, sales receipts, credit memos, refund receipts, purchases,
              bills, vendor credits, and profit-and-loss lines from journal entries into your workspace Financials.
              From Xero we sync invoices and bills, credit notes, authorised bank receive/spend transactions, and
              revenue or expense lines from posted manual journals. Synced rows store amounts, categories, counterparty
              or description names, dates, notes, currency and tax fields when present, and provider transaction ids.
              OAuth tokens are encrypted at rest. Nothing is accessed before that connection. Connecting one accounting
              provider does not disconnect the other if both are configured.
            </p>
          </section>

          <section>
            <h2 className="text-lg text-mk-black font-normal tracking-tight mb-2">SAP Business One data</h2>
            <p>
              SAP Business One data is pulled only if and when you explicitly connect it via Integrations by providing
              your Service Layer URL, company database name, username, and password. Those credentials (including the
              password and session identifiers used to sync) are encrypted at rest on Trenston servers. We sync A/R
              invoices, A/P purchase invoices, A/R credit notes, and A/P purchase credit notes into your workspace
              Financials (amounts, business partner names, comments, document dates, currency and tax fields when
              present). Nothing is accessed before that connection.
            </p>
          </section>

          <section>
            <h2 className="text-lg text-mk-black font-normal tracking-tight mb-2">Slack alerts</h2>
            <p>
              If you configure a Slack Incoming Webhook on Integrations, Trenston stores that webhook URL encrypted at
              rest and may post to the channel you choose: a one-time connection test message, and later high-severity
              Decision Engine alert titles and details with a link back to Decisions in Trenston. Trenston does not use
              a full Slack OAuth app and does not read your Slack workspace history.
            </p>
          </section>

          <section>
            <h2 className="text-lg text-mk-black font-normal tracking-tight mb-2">Payments</h2>
            <p>
              Paid subscriptions are processed by <span className="text-mk-black">Paddle</span> as merchant of record.
              Paddle collects billing details and may share limited transaction and customer identifiers with us so we can
              activate and manage your plan. We do not store full card numbers on Trenston servers.
              See our{" "}
              <Link to="/refunds" className="text-mk-navy hover:underline">Refund &amp; Billing Policy</Link>{" "}
              and the{" "}
              <Link to="/app/billing" className="text-mk-navy hover:underline">Billing</Link> page for plan details.
            </p>
          </section>

          <section>
            <h2 className="text-lg text-mk-black font-normal tracking-tight mb-2">Email</h2>
            <p>
              Transactional emails (for example invitations or notices) are sent through{" "}
              <span className="text-mk-black">Resend</span>. Email addresses and message metadata needed to deliver those
              emails are processed accordingly.
            </p>
          </section>

          <section>
            <h2 className="text-lg text-mk-black font-normal tracking-tight mb-2">AI processing</h2>
            <p>
              Trenston uses a third-party AI provider, <span className="text-mk-black">Anthropic (Claude)</span>, for
              features including Ask Trenston chat, document and bill/receipt extraction, Decision Engine suggestions,
              Weekly Pack and Briefing summaries, and report digests. Ask Trenston chat messages (your questions and
              assistant replies) are stored in Trenston&apos;s database for your user in the workspace so you can reopen
              the conversation. When you use Ask Trenston, Trenston transmits a company snapshot to Anthropic that can
              include financial figures (when your role may access Financials), pipeline and department queue data you
              can access, people-roster counts, risk and open-decision titles, plus recent chat turns for multi-turn
              context. Other AI features transmit the document or workspace records needed for that request. Anthropic
              uses that context to generate the requested response or suggested entries for your workspace. Do not
              submit data you are not authorized to process with third-party AI providers. Trenston does not claim SOC 2,
              HIPAA, GDPR, or similar certifications based solely on this disclosure.
            </p>
            <p className="mt-3">
              Trenston reaches Anthropic through its commercial API. Under Anthropic&apos;s commercial terms, inputs and
              outputs are not used to train its models by default, and Anthropic processes them on our behalf. Trenston
              itself does not train or fine-tune any model on customer data. When enabled, bill and receipt uploads may
              first be read by Google Cloud Document AI (Invoice Parser) to pull out vendor, date, and amounts, with
              Anthropic used when that parser is unavailable or not confident. That processing is run by Trenston and
              is separate from any Google account a teammate connects.
            </p>
          </section>

          <section>
            <h2 className="text-lg text-mk-black font-normal tracking-tight mb-2">Cookies &amp; session</h2>
            <p>
              We use a session/auth cookie to keep you logged in. We do not use tracking or advertising cookies.
              A small local preference may also record that you dismissed our cookie notice. You can clear cookies and
              site data in your browser.
            </p>
          </section>

          <section>
            <h2 className="text-lg text-mk-black font-normal tracking-tight mb-2">Analytics &amp; tracking</h2>
            <p>
              Trenston uses Vercel Web Analytics to count visitors and page views. It is cookieless and does not
              identify you personally. We also record first-party product usage events (for example which
              departments you enable) in our own MongoDB so we can improve Trenston. That usage data stays in
              Trenston&apos;s database and is not sent to Google Analytics or other advertising or analytics vendors.
              We do not use Google Analytics, session-recording, or advertising trackers.
            </p>
          </section>

          <section>
            <h2 className="text-lg text-mk-black font-normal tracking-tight mb-2">Where data is stored</h2>
            <ul className="list-disc pl-5 space-y-2 mt-2">
              <li><span className="text-mk-black">MongoDB Atlas</span>: primary database for account and business data</li>
              <li><span className="text-mk-black">Cloudflare R2</span>: uploaded document files (private bucket)</li>
              <li><span className="text-mk-black">Clerk</span>: authentication and login/session data</li>
              <li><span className="text-mk-black">Anthropic</span>: processes AI feature inputs (documents, Ask Trenston context, summaries)</li>
              <li><span className="text-mk-black">Google Cloud Document AI</span>: optional first read of uploaded bills and receipts</li>
              <li><span className="text-mk-black">Paddle</span>: payment processing</li>
              <li><span className="text-mk-black">Resend</span>: transactional email</li>
              <li><span className="text-mk-black">Vercel</span>: hosting and cookieless web analytics (page views)</li>
              <li><span className="text-mk-black">QuickBooks (Intuit)</span>: only for workspaces that connect it</li>
              <li><span className="text-mk-black">Xero</span>: only for workspaces that connect it</li>
              <li><span className="text-mk-black">SAP Business One</span>: only for workspaces that connect it (credentials stored encrypted; data pulled from your Service Layer)</li>
              <li><span className="text-mk-black">HubSpot</span>: only for workspaces that connect it</li>
              <li><span className="text-mk-black">Google</span>: only for teammates who connect their own Google account</li>
              <li><span className="text-mk-black">Slack</span>: only when you configure an Incoming Webhook (alert delivery to your channel)</li>
            </ul>
          </section>

          <section>
            <h2 className="text-lg text-mk-black font-normal tracking-tight mb-2">Retention &amp; deletion</h2>
            <p>
              When you delete your account, your personal data is removed from Trenston&apos;s database immediately, with
              no hold period on our side, and any workspace where you are the only owner is deleted with it. Where
              other people worked in a workspace, their history stays and your name in the activity log becomes
              &quot;Deleted user&quot;. Our database and storage providers keep their own backups for a limited time, so
              a deleted record may remain in a provider backup until it ages out.
            </p>
            <p className="mt-3">
              Workspace owners can export a data package for companies they own (database records as JSON, up to
              5,000 rows per collection, integration tokens stripped, original uploaded files not included).
              Non-owner members receive their own account data plus a summary of workspaces they belong to. Account
              export is available on every plan. You can export and delete from{" "}
              <Link to="/app/settings" className="text-mk-navy hover:underline">Account Settings</Link>
              {" "}(<span className="font-mono text-xs text-mk-gray">/app/settings</span>). The full picture is on our{" "}
              <Link to="/security#your-data" className="text-mk-navy hover:underline">Security</Link> page.
            </p>
          </section>

          <section>
            <h2 className="text-lg text-mk-black font-normal tracking-tight mb-2">Governing law</h2>
            <p>
              This policy is governed by the laws of the Philippines. This may change once the business entity is
              formally registered in another jurisdiction.
            </p>
          </section>

          <section>
            <h2 className="text-lg text-mk-black font-normal tracking-tight mb-2">Security practices</h2>
            <p>
              How Trenston protects workspaces, credentials, and uploaded files is described on our{" "}
              <Link to="/security" className="text-mk-navy hover:underline">Security</Link> page.
            </p>
          </section>

          <section>
            <h2 className="text-lg text-mk-black font-normal tracking-tight mb-2">Contact</h2>
            <p>
              Privacy questions:{" "}
              <a href={PUBLIC_CONTACT_MAILTO} className="text-mk-navy hover:underline">{PUBLIC_CONTACT_EMAIL}</a>
              {" "}· Trenston · {COMPANY_LOCATION}.
            </p>
          </section>
        </div>

        <p className="mt-12 text-xs text-mk-gray border-t border-mk-black/5 pt-6">
          This policy will be reviewed by legal counsel as Trenston grows; contact us with questions.
        </p>
      </div>
    </div>
  );
}
