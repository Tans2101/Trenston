import { useEffect, useMemo } from "react";
import { Link } from "react-router-dom";
import { motion } from "motion/react";
import { ArrowRight } from "lucide-react";
import MarketingNav from "@/components/marketing/MarketingNav";
import MarketingFooter from "@/components/marketing/MarketingFooter";
import { useMarketingAuth } from "@/hooks/useMarketingAuth";
import { CHANGELOG_INTRO, getChangelogEntries } from "@/lib/changelog";
import { CATEGORY } from "@/lib/marketingCopy";

const ease = [0.16, 1, 0.3, 1];
const fade = {
  hidden: { opacity: 0, y: 16 },
  show: (i = 0) => ({ opacity: 1, y: 0, transition: { duration: 0.6, ease, delay: i * 0.04 } }),
};

function formatDate(iso) {
  try {
    return new Date(`${iso}T12:00:00Z`).toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso;
  }
}

/** Renders only frontend/src/lib/changelog.json — never git history or CI output. */
export default function Changelog() {
  const { authed, enter } = useMarketingAuth();
  const entries = useMemo(() => getChangelogEntries(), []);
  useEffect(() => {
    window.scrollTo(0, 0);
  }, []);

  return (
    <div className="min-h-screen overflow-x-hidden bg-white text-mk-black">
      <MarketingNav authed={authed} onEnter={enter} active="/changelog" />

      <main>
        <section className="px-6 pb-12 pt-36 md:pb-16 md:pt-44">
          <div className="mx-auto max-w-3xl">
            <motion.p variants={fade} initial="hidden" animate="show" custom={0}
              className="font-mono text-xs uppercase tracking-[0.3em] text-mk-gray">
              {CATEGORY}
            </motion.p>
            <motion.h1 variants={fade} initial="hidden" animate="show" custom={1}
              className="font-display mt-8 text-5xl font-medium leading-[1.05] tracking-[-0.03em] md:text-6xl">
              Changelog
            </motion.h1>
            <motion.p variants={fade} initial="hidden" animate="show" custom={2}
              className="mt-6 max-w-2xl text-lg leading-relaxed text-mk-gray">
              {CHANGELOG_INTRO}
            </motion.p>
          </div>
        </section>

        <section className="border-t border-mk-black/[0.05] px-6 py-16 md:py-20">
          <ol className="mx-auto max-w-3xl space-y-0">
            {entries.map((entry, i) => (
              <motion.li
                key={`${entry.date}-${entry.title}`}
                variants={fade}
                initial="hidden"
                whileInView="show"
                viewport={{ once: true, margin: "-30px" }}
                custom={Math.min(i, 6)}
                className="grid gap-2 border-b border-mk-black/[0.06] py-8 first:pt-0 md:grid-cols-[7.5rem_1fr] md:gap-8"
              >
                <time dateTime={entry.date} className="font-mono text-[11px] uppercase tracking-[0.14em] text-mk-gray">
                  {formatDate(entry.date)}
                </time>
                <div>
                  <h2 className="text-base font-medium text-mk-black md:text-lg">{entry.title}</h2>
                  <p className="mt-2 text-sm leading-relaxed text-mk-gray">{entry.description}</p>
                </div>
              </motion.li>
            ))}
          </ol>
          <p className="mx-auto mt-12 max-w-3xl text-sm text-mk-gray">
            Looking for plans and users?{" "}
            <Link to="/pricing" className="text-mk-black hover:text-mk-navy transition-colors">
              See pricing
            </Link>
            . For live service health, see{" "}
            <Link to="/status" className="text-mk-black hover:text-mk-navy transition-colors">
              Status
            </Link>
            .
          </p>
        </section>

        <section className="px-6 pb-24">
          <div className="mx-auto max-w-3xl text-center">
            <button
              type="button"
              onClick={enter}
              className="mk-btn mk-btn-dark group"
            >
              {authed ? "Open cockpit" : "Get started"}
              <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
            </button>
          </div>
        </section>
      </main>

      <MarketingFooter />
    </div>
  );
}
