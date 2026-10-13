import { useEffect } from "react";
import {
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
import {
  CtaBand,
  DISPLAY,
  DrawLine,
  Eyebrow,
  MkAccordion,
  MkButton,
  MkLink,
  MkPage,
  PageHero,
  Reveal,
  RuledItem,
  SectionHeader,
  Mark,
} from "@/components/marketing/mk";
import { cn } from "@/lib/utils";
import { useMarketingAuth } from "@/hooks/useMarketingAuth";
import { TAGLINE, TESTIMONIALS } from "@/lib/marketingCopy";
import Testimonial from "@/components/marketing/Testimonial";

/**
 * Monochrome monogram tiles, not real vendor logos — trademarked marks
 * (Vercel, MongoDB, Cloudflare, Clerk, Render, Paddle) need written
 * permission we don't have. Kept black-and-white to match the site.
 */
function InfraBadge({ name }) {
  return (
    <div
      aria-hidden
      className="flex h-11 w-11 shrink-0 items-center justify-center bg-mk-black font-mono text-sm font-semibold text-white transition-colors duration-300 group-hover:bg-mk-navy"
    >
      {name.trim().charAt(0)}
    </div>
  );
}

const TRUST_BADGES = [
  { icon: LockKeyhole, label: "End-to-End TLS Encryption" },
  { icon: ShieldCheck, label: "Workspace Isolation" },
  { icon: KeyRound, label: "Fernet Token Sealing" },
  { icon: Trash2, label: "Export and Delete Anytime" },
];

const WHERE_DATA_LIVES = [
  {
    icon: Cloud,
    title: "Vercel",
    body: "The signed-in cockpit and the marketing site are served from Vercel over HTTPS.",
  },
  {
    icon: Cloud,
    title: "Render",
    body: "The API is a Python FastAPI service on Render (see render.yaml), with Render cron jobs for retention checks, accounting sync, daily alerts, and the weekly digest email.",
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
    title: "At rest: integration secrets",
    body: "OAuth tokens and ERP credentials (Google, QuickBooks, Xero, HubSpot, SAP Business One) are sealed with Fernet symmetric encryption before they are written to MongoDB. The key is INTEGRATION_ENCRYPTION_KEY in Render environment config and is never committed to the repository. Production refuses to boot without a valid key.",
  },
  {
    title: "At rest: platform storage",
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
    why: "Optional Incoming Webhook URL only, for high-severity alerts to a channel you choose. Not a full Slack OAuth app.",
  },
  {
    name: "Anthropic",
    why: "AI features (Ask Trenston, bill/receipt extract, briefing and digest summaries, decision suggestions) send the workspace context needed for that request through Anthropic's commercial API. Under Anthropic's commercial terms, inputs and outputs are not used to train its models by default, and Anthropic acts as our processor. Trenston does not train or fine-tune models on customer data.",
  },
  {
    name: "Google Cloud Document AI",
    why: "When enabled, a bill or receipt you upload may first be read by Google's Invoice Parser to pull out vendor, date, and amounts. Anything it cannot read confidently falls back to Anthropic. This is run by Trenston, not through your Google account.",
  },
  {
    name: "Clerk, Paddle, Resend, Vercel Analytics",
    why: "Auth sessions, billing as merchant of record, transactional email, and cookieless page-view analytics respectively.",
  },
];

const RETENTION = [
  "Account deletion removes your personal account data from Trenston's database immediately, with no hold period on our side. Copies in infrastructure provider backups age out on the provider's own schedule.",
  "Workspace owners can delete the company workspace; Trenston removes workspace-scoped MongoDB records and associated private R2 objects. If object storage is unreachable, deletion fails visibly so it can be retried instead of silently leaving files behind.",
  "Workspace owners can export a data package (integration tokens stripped). Non-owners get their own account data plus a membership summary.",
  "Trial and inactivity retention emails are driven by a daily Render cron (helm-retention-checks). They are reminders, not silent data deletion without the controls above.",
];

const DATA_EXIT = [
  {
    title: "It is your data",
    body: "Everything your team enters or connects stays yours. Trenston uses it to run your workspace and for nothing else: no selling, no advertising, no model training.",
  },
  {
    title: "Export it",
    body: "Any user can download their own account data from Account Settings, on any plan, including Free. Workspace owners can also download a package of the whole workspace as JSON with integration tokens stripped. The package holds database records, up to 5,000 rows per collection (a flag marks any collection that was cut), and not the original uploaded files. Financials also export as PDF and Excel, or to Google Sheets.",
  },
  {
    title: "Delete a workspace",
    body: "Owners can delete a company workspace. Trenston removes the private files from storage first, then every workspace record, then the workspace itself. If storage is unreachable the deletion stops and says so, so nothing is left behind unnoticed.",
  },
  {
    title: "Delete your account",
    body: "Deleting your account removes your personal data immediately and deletes any workspace where you are the only owner. Where other people worked in a workspace, their history is kept and your name on the activity log becomes \"Deleted user\".",
  },
  {
    title: "If you stop paying",
    body: "Paid features lock, and your data is not deleted automatically. Account export is not tied to a paid plan, so leaving never means losing your records.",
  },
  {
    title: "What can linger",
    body: "Our database and storage providers keep their own backups for a limited time, so a deleted record can exist in a provider backup until it ages out. Ask contact@trenston.com if you need specifics.",
  },
];

const STAFF_ACCESS = [
  "Trenston is founder-operated. The people who administer production (Render, Vercel, MongoDB Atlas, Cloudflare R2, Clerk, Paddle) can, in principle, reach infrastructure that holds customer data, the same as any small SaaS with shared ops credentials.",
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
    icon: KeyRound,
    title: "API keys are read-only",
    body: "Personal API keys (Growth and Business) can only read, never change data. A key sees exactly what its owner can see in Trenston, only in that workspace. Keys are stored as one-way hashes, shown once, rate limited, and revocable at any time in Settings. Assistants connected by signing in (OAuth) get the same read-only access through tokens that last 30 days and renew with rotating refresh tokens, and can be disconnected in Settings at any time, which ends access immediately.",
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
  "Google is not read-only. Connecting your Google account grants Calendar read and write, Gmail snippets plus drafts, Sheets export, and Drive files you pick in Trenston. It is not a full mailbox or Drive dump.",
  "Workspaces that connected Google under the original Calendar + Gmail read grant keep that narrower access until an owner reconnects and accepts the wider consent screen.",
  "Payment card details are handled by Paddle, not stored on Trenston servers.",
  "Authentication is handled by Clerk using secure session controls.",
  "Sensitive credentials and provider token responses are excluded from application logs.",
  "Uploaded documents are sent to Anthropic (and, when enabled, Google Cloud Document AI) only when an AI extract feature needs to process them.",
  "GitHub is listed as coming soon in the product catalog. It is not a live data connection today.",
];

const AI_ACCESS = [
  {
    title: "Read-only by design",
    body: "The public API has read endpoints only, and every tool in the Trenston MCP connector is marked read-only. There is no way to create, edit, approve, or delete anything in Trenston through an API key or a connected assistant.",
  },
  {
    title: "It sees what you see, nothing more",
    body: "Every request runs through the same permission checks as the app: one workspace only, your departments only, and financial figures only if you have Financials access. If your access changes, the API changes with it on the next request.",
  },
  {
    title: "Sign in, or use a key",
    body: "Assistants such as Claude connect by sending you to a Trenston consent screen (OAuth 2.1 with PKCE). Scripts and tools like Claude Code can use a personal API key instead. Both are available on the Growth and Business plans.",
  },
  {
    title: "Expiring tokens, hashed keys",
    body: "Assistant sign-in tokens last 30 days and renew with a refresh token that changes on every use; a reused old refresh token ends the connection. API keys are shown once and stored only as a one-way hash, so Trenston cannot show them to anyone again.",
  },
  {
    title: "You can switch it off instantly",
    body: "Revoke a key or disconnect an assistant in Settings, under API keys, and it stops working on the next request. Removing someone from the workspace ends all of their keys and connections for good, and deleting a workspace or account deletes them.",
  },
  {
    title: "A consent screen that tells the truth",
    body: "Before anything connects, the consent screen shows which workspace, exactly what can be read, and where the sign-in returns. Only Claude's own address is shown as verified; any other app is labeled unverified, because an app chooses its own name.",
  },
  {
    title: "Limits and separation",
    body: "Each key is limited to 60 requests a minute. API keys and assistant tokens only work on the public read-only API, never on the signed-in app, and Gmail data is never included in what assistants receive.",
  },
  {
    title: "What leaves Trenston",
    body: "When you ask a connected assistant a question, it receives the data its tools read for you, and that provider's terms then apply. Text your team wrote, such as task titles, is passed as data, and the connector tells assistants never to treat it as instructions.",
  },
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
    a: "Connecting your Google account requests Calendar read and write (Trenston can create or update events when you ask), Gmail read for briefing snippets plus gmail.compose for drafts only (not gmail.send), Google Sheets to create a Financials export spreadsheet, and drive.file so you can pick a bill in Drive. Google’s consent screen may label compose as managing drafts and sending; Trenston only posts to Gmail’s drafts API. Each teammate connects their own Google account, never a shared workspace mailbox. Reconnect Google to add missing write scopes.",
  },
  {
    q: "Who can see uploaded bills and legal files?",
    a: "Authorized people in your workspace. Files sit in a private bucket and are served through short-lived signed links, not public URLs.",
  },
  {
    q: "Can an AI assistant change anything in our workspace?",
    a: "No. API keys and connected assistants are read-only. They can read your briefing, decisions, tasks, your assigned work and, with Financials access, a financial summary. They cannot create, edit, approve, or delete anything.",
  },
  {
    q: "How do we cut off an assistant or a key?",
    a: "In Settings, under API keys: revoke a key or disconnect an app, and it stops working on the next request. Removing a teammate from the workspace ends all of their keys and connections permanently.",
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

  const toc = [
    { id: "infrastructure", label: "Infrastructure" },
    { id: "encryption", label: "Encryption" },
    { id: "third-parties", label: "Third parties" },
    { id: "ai-assistants", label: "API keys and AI assistants" },
    { id: "retention", label: "Retention and access" },
    { id: "your-data", label: "Your data, your exit" },
    { id: "questions", label: "Common questions" },
  ];

  return (
    <MkPage authed={authed} onEnter={enter} active="/security">
      <PageHero
        eyebrow="Security at Trenston"
        lines={["Your company runs on trust.", <>Trenston is built to <Mark dark>protect</Mark> it.</>]}
        sub="Cash, decisions, documents, and connected systems are the operating picture of a company. Trenston is designed so that picture stays inside the workspace that owns it, from sign-in through deletion."
        toc={toc}
        size="md"
      >
        <ul className="flex flex-wrap gap-x-6 gap-y-3" data-testid="security-trust-badges">
          {TRUST_BADGES.map(({ icon: Icon, label }) => (
            <li key={label} className="inline-flex items-center gap-2 text-sm text-white">
              <Icon className="h-4 w-4" strokeWidth={1.5} aria-hidden />
              {label}
            </li>
          ))}
        </ul>
        <p className="mt-8 flex flex-wrap items-center gap-x-5 gap-y-2 text-sm text-mk-gray-dark">
          <span>Last updated October 12, 2026</span>
          <MkLink to="/status" className="text-white">Status</MkLink>
          <MkLink to="/changelog" className="text-white">Changelog</MkLink>
          <MkLink to="/privacy" className="text-white">Privacy</MkLink>
        </p>
      </PageHero>

      {/* Why this matters */}
      <section className="bg-white px-6 py-24 md:py-28">
        <div className="mx-auto grid max-w-7xl gap-12 lg:grid-cols-2">
          <Reveal>
            <Eyebrow>Why this matters</Eyebrow>
            <h2 className={cn("mt-4 text-4xl leading-[1.05] md:text-5xl", DISPLAY)}>
              Companies cannot treat a cockpit as optional infrastructure.
            </h2>
          </Reveal>
          <Reveal i={1} className="self-end">
            <DrawLine className="bg-mk-black" />
            <p className="mt-8 text-xl leading-relaxed text-mk-black">
              Trenston holds the numbers leadership uses to decide, the files finance and legal attach, and the
              tokens that connect accounting, CRM, and calendar. That is why security is part of the product, not a
              footnote on a pricing page.
            </p>
          </Reveal>
        </div>
      </section>

      {/* Customer voice */}
      <section className="bg-white px-6 pb-24 md:pb-28" aria-label="What customers say">
        <Testimonial item={TESTIMONIALS[0]} />
      </section>

      {/* Infrastructure */}
      <section id="infrastructure" className="scroll-mt-16 bg-mk-mist px-6 py-24 md:py-28">
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="Infrastructure"
            title="Every part of the stack has one job."
            intro="Business records sit in MongoDB Atlas, private files in Cloudflare R2, identity in Clerk, and payments in Paddle, each on infrastructure built for that job."
          />
          <div className="mt-14 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {WHERE_DATA_LIVES.map(({ icon: Icon, title, body }, i) => (
              <Reveal key={title} i={i % 3} className="mk-card group flex flex-col p-7">
                <div className="flex items-center justify-between">
                  <InfraBadge name={title} />
                  <Icon className="h-5 w-5 text-mk-navy" strokeWidth={1.5} aria-hidden />
                </div>
                <h3 className="mt-8 text-xl font-semibold tracking-tight">{title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-mk-gray">{body}</p>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* Encryption — flat black band */}
      <section id="encryption" className="scroll-mt-16 bg-mk-black px-6 py-24 text-white md:py-28">
        <div className="mx-auto max-w-7xl">
          <SectionHeader dark eyebrow="Encryption" title="What is encrypted, and how." />
          <div className="mt-14 grid gap-12 md:grid-cols-3 md:gap-10">
            {ENCRYPTION.map((item, i) => (
              <RuledItem
                key={item.title}
                dark
                i={i}
                icon={[LockKeyhole, KeyRound, Database][i] || ShieldCheck}
                title={item.title}
                body={item.body}
              />
            ))}
          </div>
        </div>
      </section>

      {/* Third parties */}
      <section id="third-parties" className="scroll-mt-16 bg-white px-6 py-24 md:py-28">
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="Third parties"
            title="Who receives data, and why."
            intro="Cross-checked against the product integration catalog. Optional connections only run after someone in your workspace connects them. Platform providers below are required to operate Trenston itself."
            action={<MkLink to="/integrations" className="text-mk-navy">Public integrations page</MkLink>}
          />
          <div className="mt-14 border-t border-mk-black">
            {THIRD_PARTIES.map((item, i) => (
              <Reveal
                key={item.name}
                i={i % 3}
                className="group grid gap-3 border-b border-mk-line py-7 md:grid-cols-[3rem_18rem_1fr] md:gap-8"
              >
                <span className="font-mono text-sm text-mk-gray">{String(i + 1).padStart(2, "0")}</span>
                <p className="text-lg font-semibold tracking-tight text-mk-black">
                  <span className="mk-title-line">{item.name}</span>
                </p>
                <p className="leading-relaxed text-mk-gray">{item.why}</p>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* API keys and AI assistants */}
      <section id="ai-assistants" className="scroll-mt-16 bg-mk-black px-6 py-24 text-white md:py-28" data-testid="security-ai-access">
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            dark
            eyebrow="API keys and AI assistants"
            title="Connect AI, without handing it the keys."
            intro="You can let Claude or your own tools read your Trenston workspace. Here is exactly what that allows, and what it never will."
            action={<MkLink to="/help#ai-assistants" className="text-white">How to connect</MkLink>}
          />
          <div className="mt-14 grid gap-x-10 gap-y-12 sm:grid-cols-2 lg:grid-cols-4">
            {AI_ACCESS.map((item, i) => (
              <RuledItem key={item.title} dark i={i % 4} index={i + 1} title={item.title} body={item.body} />
            ))}
          </div>
        </div>
      </section>

      {/* Retention + staff access */}
      <section id="retention" className="scroll-mt-16 bg-mk-mist px-6 py-24 md:py-28">
        <div className="mx-auto grid max-w-7xl gap-14 lg:grid-cols-2">
          {[
            { eyebrow: "Retention & deletion", title: "How long data stays", lines: RETENTION, icon: Trash2 },
            { eyebrow: "Who at Trenston can access data", title: "Staff access", lines: STAFF_ACCESS, icon: UserRoundCheck },
          ].map(({ eyebrow, title, lines, icon: Icon }, i) => (
            <Reveal key={title} i={i} className="mk-item group">
              <div className="flex items-center justify-between">
                <Eyebrow>{eyebrow}</Eyebrow>
                <Icon className="h-6 w-6 text-mk-navy" strokeWidth={1.5} aria-hidden />
              </div>
              <h2 className={cn("mt-5 text-3xl", DISPLAY)}>{title}</h2>
              <ul className="mt-8 space-y-5">
                {lines.map((line) => (
                  <li key={line} className="flex gap-3 leading-relaxed text-mk-gray">
                    <Check className="mt-1 h-4 w-4 shrink-0 text-mk-navy" aria-hidden />
                    <span>{line}</span>
                  </li>
                ))}
              </ul>
            </Reveal>
          ))}
        </div>
      </section>

      {/* Your data, your exit */}
      <section id="your-data" className="scroll-mt-16 bg-white px-6 py-24 md:py-28">
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="Your data, your exit"
            title="Take it with you, or erase it."
            intro="You should never be locked in by your own records. Here is exactly what you can export and delete, and what to expect afterwards."
            action={<MkLink to="/app/settings" className="text-mk-navy">Account Settings</MkLink>}
          />
          <div className="mt-14 grid gap-x-10 gap-y-14 sm:grid-cols-2 lg:grid-cols-3">
            {DATA_EXIT.map(({ title, body }, i) => (
              <RuledItem key={title} i={i % 3} index={i + 1} icon={[Database, Cloud, Trash2, UserRoundCheck, CreditCard, ShieldCheck][i] || ShieldCheck} title={title} body={body} />
            ))}
          </div>
        </div>
      </section>

      {/* Layered controls */}
      <section className="bg-white px-6 py-24 md:py-28">
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            eyebrow="Layered protection"
            title="Protection built into every layer."
            intro="No single control carries the whole burden. Trenston combines encryption, access boundaries, private storage, validation, and deletion that is meant to complete."
          />
          <div className="mt-14 grid gap-x-10 gap-y-14 sm:grid-cols-2 lg:grid-cols-3">
            {CONTROLS.map(({ icon, title, body }, i) => (
              <RuledItem key={title} i={i % 3} index={i + 1} icon={icon} title={title} body={body} />
            ))}
          </div>
        </div>
      </section>

      {/* Data boundaries — black band checklist */}
      <section className="bg-mk-black px-6 py-24 text-white md:py-28">
        <div className="mx-auto max-w-7xl">
          <SectionHeader
            dark
            eyebrow="Data boundaries"
            title="Clear about where data goes."
            intro="Trenston is not the only system involved in delivering the product. We identify the providers we use and limit each integration to the access needed for its feature."
            action={<MkLink to="/privacy" className="text-white">Read the Privacy Policy</MkLink>}
          />
          <ul className="mt-14 grid gap-x-12 border-t border-white/30 md:grid-cols-2">
            {PRACTICES.map((practice, i) => (
              <Reveal as="li" key={practice} i={i % 2} className="flex gap-4 border-b border-white/15 py-6">
                <Check className="mt-1 h-4 w-4 shrink-0 text-white" aria-hidden />
                <span className="leading-relaxed text-white/85">{practice}</span>
              </Reveal>
            ))}
          </ul>
        </div>
      </section>

      {/* FAQ */}
      <section id="questions" className="scroll-mt-16 bg-white px-6 py-24 md:py-28">
        <div className="mx-auto grid max-w-7xl gap-12 lg:grid-cols-[0.8fr_1.2fr]">
          <Reveal>
            <Eyebrow>Common questions</Eyebrow>
            <h2 className={cn("mt-4 text-4xl leading-[1.05] md:text-5xl", DISPLAY)}>What leadership teams ask.</h2>
          </Reveal>
          <Reveal i={1}>
            <MkAccordion items={QUESTIONS} idPrefix="security-faq" />
          </Reveal>
        </div>
      </section>

      {/* Honest security — letter-style callout */}
      <section className="bg-white px-6 pb-24">
        <Reveal className="mx-auto grid max-w-7xl gap-8 border-l-4 border-mk-navy bg-mk-mist p-8 md:grid-cols-[1fr_auto] md:items-center md:p-12">
          <div>
            <Eyebrow>Honest security</Eyebrow>
            <h2 className={cn("mt-4 text-3xl", DISPLAY)}>Security is ongoing work.</h2>
            <p className="mt-4 max-w-2xl leading-relaxed text-mk-gray">
              We do not claim certifications we have not earned or promise that any system is invulnerable. We
              review Trenston&apos;s controls, address identified risks, and communicate our current practices plainly.
            </p>
          </div>
          <MkButton variant="dark" href="mailto:contact@trenston.com?subject=Trenston%20security%20report">
            Report a concern privately
          </MkButton>
        </Reveal>
      </section>

      <CtaBand
        title={TAGLINE}
        sub="Sign in with Google or email. Your workspace stays yours, from sign-in through deletion."
        authed={authed}
        onEnter={enter}
      />
    </MkPage>
  );
}
