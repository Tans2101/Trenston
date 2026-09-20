import { useEffect } from "react";
import { Link } from "react-router-dom";
import { motion } from "motion/react";
import {
  ArrowRight,
  Check,
  Cloud,
  CreditCard,
  Database,
  FileCheck2,
  KeyRound,
  LockKeyhole,
  ShieldCheck,
  Trash2,
  UserRoundCheck,
} from "lucide-react";
import MarketingNav from "@/components/marketing/MarketingNav";
import MarketingFooter from "@/components/marketing/MarketingFooter";
import { useMarketingAuth } from "@/hooks/useMarketingAuth";

const ease = [0.16, 1, 0.3, 1];
const fade = {
  hidden: { opacity: 0, y: 18 },
  show: (i = 0) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.65, ease, delay: i * 0.08 },
  }),
};

const WHERE_DATA_LIVES = [
  {
    icon: Cloud,
    title: "Application hosting",
    body: "The signed-in cockpit and marketing site run on Vercel. The API is a Python FastAPI service on Render (see render.yaml), with Render cron jobs for retention checks, accounting sync, daily alerts, and weekly digest email.",
  },
  {
    icon: Database,
    title: "MongoDB Atlas",
    body: "Primary company data (workspaces, financials, pipeline, decisions, and team records) lives in a dedicated MongoDB Atlas database (DB_NAME=trenston), not in the browser and not in a Render-managed Mongo sidecar.",
  },
  {
    icon: Cloud,
    title: "Cloudflare R2",
    body: "Uploaded bills, receipts, and legal files are stored in a private object bucket. Files are not publicly listed and are retrieved with short-lived signed links.",
  },
  {
    icon: UserRoundCheck,
    title: "Clerk",
    body: "Sign-in identity and authentication sessions are handled by Clerk (clerk.trenston.com). Trenston stores the account details needed to run your workspace, not payment cards.",
  },
  {
    icon: CreditCard,
    title: "Paddle",
    body: "Paid subscriptions go through Paddle as merchant of record. Card numbers never pass through Trenston’s application database.",
  },
];

const ENCRYPTION = [
  {
    title: "In transit",
    body: "Production traffic uses HTTPS end to end: browsers talk to Vercel over TLS; the API on Render serves HTTPS; outbound calls to Clerk, Paddle, Anthropic, Google, QuickBooks, Xero, HubSpot, SAP Business One, Resend, and R2 use TLS.",
  },
  {
    title: "At rest — integration secrets",
    body: "OAuth tokens and ERP credentials (Google, QuickBooks, Xero, HubSpot, SAP Business One) are sealed with Fernet symmetric encryption before they are written to MongoDB. The key is INTEGRATION_ENCRYPTION_KEY in Render environment config — never committed to the repository. Production refuses to boot without a valid key.",
  },
  {
    title: "At rest — platform storage",
    body: "MongoDB Atlas and Cloudflare R2 provide their own encrypted storage for the clusters and buckets Trenston uses. Trenston does not claim an additional application-level encryption layer over every document field beyond credential sealing described above.",
  },
];

const THIRD_PARTIES = [
  {
    name: "Google",
    why: "Optional, per-user Calendar and Gmail (plus Sheets export and Drive file pick when you grant those scopes). Tokens are personal to the teammate who connected.",
  },
  {
    name: "QuickBooks / Xero / SAP Business One",
    why: "Optional accounting sync into Financials when a workspace owner or the teammate who connected the system triggers it. SAP uses Service Layer credentials you supply; QB/Xero use OAuth.",
  },
  {
    name: "HubSpot",
    why: "Optional CRM deal sync into Pipeline and Telemetry when connected.",
  },
  {
    name: "Slack",
    why: "Optional Incoming Webhook URL only — high-severity alerts to a channel you choose. Not a full Slack OAuth app.",
  },
  {
    name: "Anthropic",
    why: "AI features (Ask Trenston, bill/receipt extract, briefing and digest summaries, decision suggestions) send the minimum workspace context needed for that request.",
  },
  {
    name: "Clerk, Paddle, Resend, Vercel Analytics",
    why: "Auth sessions, billing as merchant of record, transactional email, and cookieless page-view analytics respectively.",
  },
];

const RETENTION = [
  "Account deletion wipes personal account data immediately — there is no post-deletion hold period for that wipe path.",
  "Workspace owners can delete the company workspace; Trenston removes workspace-scoped MongoDB records and associated private R2 objects. If object storage is unreachable, deletion fails visibly so it can be retried instead of silently leaving files behind.",
  "Workspace owners can export a data package (integration tokens stripped). Non-owners get their own account data plus a membership summary.",
  "Trial and inactivity retention emails are driven by a daily Render cron (helm-retention-checks) — reminders, not silent data deletion without the controls above.",
];

const STAFF_ACCESS = [
  "Trenston is founder-operated. The people who administer production (Render, Vercel, MongoDB Atlas, Cloudflare R2, Clerk, Paddle) can, in principle, reach infrastructure that holds customer data — the same as any small SaaS with shared ops credentials.",
  "There is no separate large support organization with standing read access to every workspace. We do not browse customer financials or documents for marketing or product curiosity.",
  "When access is needed to debug a customer-reported issue, we do it for that purpose and with the customer’s knowledge whenever practical. Prefer contacting contact@trenston.com for security or access questions.",
];

const CONTROLS = [
  {
    icon: KeyRound,
    title: "Credentials encrypted at rest",
    body: "OAuth tokens for Google, QuickBooks, Xero, and HubSpot, plus SAP Business One credentials, are Fernet-encrypted before they are stored. Encryption keys come from protected environment configuration, never from the codebase.",
  },
  {
    icon: UserRoundCheck,
    title: "Access stays in its lane",
    body: "Each workspace is isolated. Role-based packs and department access limit people to the company data and actions they are authorized to use.",
  },
  {
    icon: Cloud,
    title: "Private file storage",
    body: "Uploaded documents stay in a private Cloudflare R2 bucket. Downloads use time-limited signed URLs rather than public file links.",
  },
  {
    icon: FileCheck2,
    title: "Uploads are inspected",
    body: "Trenston enforces a 15 MB size cap and checks PDF, PNG, and JPEG file signatures before accepting a document, reducing the risk from disguised or oversized files.",
  },
  {
    icon: ShieldCheck,
    title: "Safer web defaults",
    body: "HTTPS, restrictive browser security headers on Vercel and the API, protected administrative diagnostics, and no-store API responses reduce exposure in browsers and intermediaries.",
  },
  {
    icon: Trash2,
    title: "Deletion is designed to finish",
    body: "Workspace deletion removes workspace-scoped database records and associated private files. If object storage is unavailable, Trenston fails visibly so deletion can be retried instead of silently leaving files behind.",
  },
];

const PRACTICES = [
  "Integration access is opt-in and can be disconnected at any time.",
  "Google Calendar and Gmail are personal: each teammate connects their own Google account and only sees their meetings and threads. Shared company OAuth (QuickBooks, Xero, HubSpot, SAP) can be used only by the teammate who connected them, or by a workspace owner. Legacy unstamped company connections are limited to owners until someone reconnects.",
  "Google is not read-only. Connecting your Google account grants Calendar read and write, Gmail snippets plus drafts, Sheets export, and Drive files you pick in Trenston — not a full mailbox or Drive dump.",
  "Workspaces that connected Google under the original Calendar + Gmail read grant keep that narrower access until an owner reconnects and accepts the wider consent screen.",
  "Payment card details are handled by Paddle, not stored on Trenston servers.",
  "Authentication is handled by Clerk using secure session controls.",
  "Sensitive credentials and provider token responses are excluded from application logs.",
  "Uploaded documents are sent to Anthropic only when an AI extract feature needs to process them.",
  "GitHub is listed as coming soon in the product catalog — it is not a live data connection today.",
];

const QUESTIONS = [
  {
    q: "Can other companies see our workspace?",
    a: "No. Queries are scoped to the signed-in workspace. Members of another company cannot read your financials, documents, or decisions.",
  },
  {
    q: "Does Trenston store our full email inbox?",
    a: "No. Trenston reads Gmail metadata and short snippets (sender, subject, preview, thread link) for the briefing. Full message bodies are not stored as a mailbox archive. If compose access is granted, Trenston can create a Gmail draft when you click Draft reply. It does not send mail. You send from Gmail.",
  },
  {
    q: "What Google access does Trenston request now?",
    a: "Connecting your Google account requests Calendar read and write (Trenston can create or update events when you ask), Gmail read for briefing snippets plus gmail.compose for drafts only (not gmail.send), Google Sheets to create a Financials export spreadsheet, and drive.file so you can pick a bill in Drive. Google’s consent screen may label compose as managing drafts and sending; Trenston only posts to Gmail’s drafts API. Each teammate connects their own Google — never a shared workspace mailbox. Reconnect Google to add missing write scopes.",
  },
  {
    q: "Who can see uploaded bills and legal files?",
    a: "Authorized people in your workspace. Files sit in a private bucket and are served through short-lived signed links, not public URLs.",
  },
  {
    q: "Is Trenston SOC 2 or ISO 27001 certified?",
    a: "Not yet. We do not claim SOC 2, ISO 27001, HIPAA, or similar certifications we have not earned. This page describes the controls that are in the product and infrastructure today.",
  },
  {
    q: "Where is the API hosted?",
    a: "Render (web service helm-company-cockpit), with MongoDB Atlas as the database. The frontend is on Vercel. Health is exposed at /api/health and summarized on the public Status page.",
  },
];

export default function Security() {
  const { authed, enter } = useMarketingAuth();

  useEffect(() => {
    window.scrollTo(0, 0);
    document.title = "Security at Trenston";
  }, []);

  return (
    <div className="min-h-screen overflow-x-hidden bg-helm-cream text-helm-navy">
      <MarketingNav authed={authed} onEnter={enter} active="/security" />

      <main>
        <section className="relative px-6 pb-16 pt-36 md:pb-24 md:pt-44 bg-helm-cream">
          <div className="relative mx-auto max-w-4xl text-center">
            <motion.div
              variants={fade}
              initial="hidden"
              animate="show"
              custom={0}
              className="mx-auto inline-flex items-center gap-2 rounded-full border border-helm-gold/35 bg-helm-gold/12 px-3 py-1.5"
            >
              <LockKeyhole className="h-3.5 w-3.5 text-helm-gold" />
              <span className="font-mono text-[10px] uppercase tracking-[0.24em] text-helm-gold">
                Security at Trenston
              </span>
            </motion.div>
            <motion.h1
              variants={fade}
              initial="hidden"
              animate="show"
              custom={1}
              className="font-display mx-auto mt-7 max-w-3xl text-4xl font-medium leading-[1.08] tracking-tight md:text-6xl"
            >
              Your company runs on trust.
              <span className="block text-helm-slate">Trenston is built to protect it.</span>
            </motion.h1>
            <motion.p
              variants={fade}
              initial="hidden"
              animate="show"
              custom={2}
              className="mx-auto mt-7 max-w-2xl text-base leading-relaxed text-helm-slate md:text-lg"
            >
              Cash, decisions, documents, and connected systems are the operating picture of a company.
              Trenston is designed so that picture stays inside the workspace that owns it, from sign-in through deletion.
            </motion.p>
            <motion.p
              variants={fade}
              initial="hidden"
              animate="show"
              custom={3}
              className="mt-5 font-mono text-[11px] uppercase tracking-[0.18em] text-helm-slate"
            >
              Last updated September 19, 2026
            </motion.p>
            <motion.p
              variants={fade}
              initial="hidden"
              animate="show"
              custom={4}
              className="mt-4 text-sm text-helm-slate"
            >
              Also see{" "}
              <Link to="/status" className="text-helm-gold hover:underline">Status</Link>
              {" · "}
              <Link to="/changelog" className="text-helm-gold hover:underline">Changelog</Link>
              {" · "}
              <Link to="/privacy" className="text-helm-gold hover:underline">Privacy</Link>
            </motion.p>
          </div>
        </section>

        <section className="border-y border-helm-navy/[0.05] px-6 py-16 md:py-20">
          <div className="mx-auto max-w-5xl">
            <p className="font-mono text-xs uppercase tracking-[0.28em] text-helm-gold">Why this matters</p>
            <h2 className="font-display mt-4 max-w-3xl text-3xl font-medium tracking-tight md:text-4xl">
              Companies cannot treat a cockpit as optional infrastructure.
            </h2>
            <p className="mt-5 max-w-3xl leading-relaxed text-helm-slate">
              Trenston holds the numbers leadership uses to decide, the files finance and legal attach,
              and the tokens that connect accounting, CRM, and calendar. That is why security is
              part of the product, not a footnote on a pricing page.
            </p>
          </div>
        </section>

        <section className="px-6 py-20 md:py-24">
          <div className="mx-auto max-w-5xl">
            <div className="max-w-2xl">
              <p className="font-mono text-xs uppercase tracking-[0.28em] text-helm-gold">Where data lives</p>
              <h2 className="font-display mt-4 text-3xl font-medium tracking-tight md:text-4xl">
                Cloudflare is for files. The company record is MongoDB.
              </h2>
              <p className="mt-4 leading-relaxed text-helm-slate">
                Trenston is not a Cloudflare database product. Business records sit in MongoDB Atlas.
                Cloudflare R2 holds private uploaded files. Identity and payments use specialized providers.
              </p>
            </div>
            <div className="mt-12 grid gap-4 sm:grid-cols-2">
              {WHERE_DATA_LIVES.map(({ icon: Icon, title, body }, index) => (
                <motion.article
                  key={title}
                  variants={fade}
                  initial="hidden"
                  whileInView="show"
                  viewport={{ once: true, margin: "-40px" }}
                  custom={index}
                  className="rounded-2xl border border-helm-navy/[0.07] bg-white p-6"
                >
                  <Icon className="h-5 w-5 text-helm-gold" />
                  <h3 className="mt-4 text-base font-medium text-helm-navy">{title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-helm-slate">{body}</p>
                </motion.article>
              ))}
            </div>
          </div>
        </section>

        <section className="border-y border-helm-navy/[0.05] px-6 py-20 md:py-24">
          <div className="mx-auto max-w-5xl">
            <p className="font-mono text-xs uppercase tracking-[0.28em] text-helm-gold">Encryption</p>
            <h2 className="font-display mt-4 max-w-3xl text-3xl font-medium tracking-tight md:text-4xl">
              What is encrypted, and how
            </h2>
            <div className="mt-10 grid gap-4 md:grid-cols-3">
              {ENCRYPTION.map((item) => (
                <article key={item.title} className="rounded-2xl border border-helm-navy/[0.07] bg-white p-6">
                  <h3 className="text-sm font-medium text-helm-navy">{item.title}</h3>
                  <p className="mt-3 text-sm leading-relaxed text-helm-slate">{item.body}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="px-6 py-20 md:py-24">
          <div className="mx-auto max-w-5xl">
            <p className="font-mono text-xs uppercase tracking-[0.28em] text-helm-gold">Third parties</p>
            <h2 className="font-display mt-4 max-w-3xl text-3xl font-medium tracking-tight md:text-4xl">
              Who receives data, and why
            </h2>
            <p className="mt-4 max-w-3xl text-sm leading-relaxed text-helm-slate">
              Cross-checked against the product integration catalog. Optional connections only run after someone in your
              workspace connects them. Platform providers below are required to operate Trenston itself.
            </p>
            <ul className="mt-10 space-y-3">
              {THIRD_PARTIES.map((item) => (
                <li key={item.name} className="rounded-xl border border-helm-navy/[0.06] bg-helm-fg/[0.02] p-5 md:grid md:grid-cols-[14rem_1fr] md:gap-6">
                  <p className="text-sm font-medium text-helm-navy">{item.name}</p>
                  <p className="mt-2 text-sm leading-relaxed text-helm-slate md:mt-0">{item.why}</p>
                </li>
              ))}
            </ul>
            <Link to="/integrations" className="mt-6 inline-flex items-center gap-2 text-sm text-helm-gold hover:text-helm-gold-hover">
              Public integrations page <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
        </section>

        <section className="border-y border-helm-navy/[0.05] bg-helm-cream px-6 py-20 md:py-24">
          <div className="mx-auto grid max-w-5xl gap-12 md:grid-cols-2">
            <div>
              <p className="font-mono text-xs uppercase tracking-[0.28em] text-helm-gold">Retention &amp; deletion</p>
              <h2 className="font-display mt-4 text-3xl font-medium tracking-tight">How long data stays</h2>
              <ul className="mt-6 space-y-3">
                {RETENTION.map((line) => (
                  <li key={line} className="flex gap-3 text-sm leading-relaxed text-helm-slate">
                    <Check className="mt-0.5 h-4 w-4 shrink-0 text-helm-gold" aria-hidden />
                    <span>{line}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <p className="font-mono text-xs uppercase tracking-[0.28em] text-helm-gold">Who at Trenston can access data</p>
              <h2 className="font-display mt-4 text-3xl font-medium tracking-tight">Staff access</h2>
              <ul className="mt-6 space-y-3">
                {STAFF_ACCESS.map((line) => (
                  <li key={line} className="flex gap-3 text-sm leading-relaxed text-helm-slate">
                    <Check className="mt-0.5 h-4 w-4 shrink-0 text-helm-gold" aria-hidden />
                    <span>{line}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </section>

        <section className="border-y border-helm-navy/[0.05] bg-helm-cream px-6 py-20 md:py-28">
          <div className="mx-auto max-w-5xl">
            <div className="max-w-2xl">
              <p className="font-mono text-xs uppercase tracking-[0.28em] text-helm-gold">Layered protection</p>
              <h2 className="font-display mt-4 text-3xl font-medium tracking-tight md:text-4xl">
                Controls across the data lifecycle
              </h2>
              <p className="mt-4 leading-relaxed text-helm-slate">
                No single control carries the whole burden. Trenston combines encryption, access boundaries,
                private storage, validation, and deletion that is meant to complete.
              </p>
            </div>

            <div className="mt-12 grid gap-px overflow-hidden rounded-2xl border border-helm-navy/[0.07] bg-helm-fg/[0.07] md:grid-cols-2">
              {CONTROLS.map(({ icon: Icon, title, body }, index) => (
                <motion.article
                  key={title}
                  variants={fade}
                  initial="hidden"
                  whileInView="show"
                  viewport={{ once: true, margin: "-50px" }}
                  custom={index % 2}
                  className="bg-white p-7 md:p-8"
                >
                  <Icon className="h-5 w-5 text-helm-gold" />
                  <h3 className="mt-5 text-base font-medium text-helm-navy">{title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-helm-slate">{body}</p>
                </motion.article>
              ))}
            </div>
          </div>
        </section>

        <section className="px-6 py-20 md:py-24">
          <div className="mx-auto grid max-w-5xl gap-12 md:grid-cols-[0.8fr_1.2fr] md:gap-20">
            <div>
              <p className="font-mono text-xs uppercase tracking-[0.28em] text-helm-gold">Data boundaries</p>
              <h2 className="font-display mt-4 text-3xl font-medium tracking-tight">
                Clear about where data goes
              </h2>
              <p className="mt-4 text-sm leading-relaxed text-helm-slate">
                Trenston is not the only system involved in delivering the product. We identify the providers
                we use and limit each integration to the access needed for its feature.
              </p>
              <Link to="/privacy" className="mt-6 inline-flex items-center gap-2 text-sm text-helm-gold hover:text-helm-gold-hover">
                Read the Privacy Policy <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            </div>

            <ul className="grid gap-3 sm:grid-cols-2">
              {PRACTICES.map((practice) => (
                <li key={practice} className="flex gap-3 rounded-xl border border-helm-navy/[0.06] bg-helm-fg/[0.02] p-4">
                  <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-helm-gold/12">
                    <Check className="h-3 w-3 text-helm-gold" />
                  </span>
                  <span className="text-sm leading-relaxed text-helm-slate">{practice}</span>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="border-y border-helm-navy/[0.05] bg-helm-cream px-6 py-20 md:py-24">
          <div className="mx-auto max-w-5xl">
            <p className="font-mono text-xs uppercase tracking-[0.28em] text-helm-gold">Common questions</p>
            <h2 className="font-display mt-4 text-3xl font-medium tracking-tight">What leadership teams ask</h2>
            <div className="mt-10 grid gap-6 md:grid-cols-2">
              {QUESTIONS.map((item) => (
                <div key={item.q} className="rounded-2xl border border-helm-navy/[0.06] bg-white p-6">
                  <h3 className="text-sm font-medium text-helm-navy">{item.q}</h3>
                  <p className="mt-3 text-sm leading-relaxed text-helm-slate">{item.a}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="px-6 py-20 md:py-24">
          <div className="mx-auto max-w-4xl rounded-2xl border border-helm-navy/[0.07] bg-white p-8 md:p-12">
            <div className="grid gap-8 md:grid-cols-[1fr_auto] md:items-end">
              <div>
                <p className="font-mono text-xs uppercase tracking-[0.28em] text-helm-gold">Honest security</p>
                <h2 className="font-display mt-4 text-3xl font-medium tracking-tight">
                  Security is ongoing work.
                </h2>
                <p className="mt-4 max-w-2xl text-sm leading-relaxed text-helm-slate">
                  We do not claim certifications we have not earned or promise that any system is
                  invulnerable. We review Trenston&apos;s controls, address identified risks, and communicate
                  our current practices plainly.
                </p>
                <p className="mt-4 text-sm text-helm-slate">
                  Found a security concern?{" "}
                  <a className="text-helm-gold hover:underline" href="mailto:contact@trenston.com?subject=Trenston%20security%20report">
                    Report it privately
                  </a>
                  .
                </p>
              </div>
              <button
                type="button"
                onClick={enter}
                className="group inline-flex items-center justify-center gap-2 rounded-full bg-helm-gold px-6 py-3 text-sm font-medium text-helm-navy transition-colors hover:bg-helm-gold-hover"
              >
                {authed ? "Open your cockpit" : "Get started securely"}
                <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
              </button>
            </div>
          </div>
        </section>
      </main>

      <MarketingFooter />
    </div>
  );
}
