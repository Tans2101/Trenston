import { useEffect } from "react";
import { Link } from "react-router-dom";
import { motion } from "motion/react";
import { ArrowRight } from "lucide-react";
import MarketingNav from "@/components/marketing/MarketingNav";
import MarketingFooter from "@/components/marketing/MarketingFooter";
import { useMarketingAuth } from "@/hooks/useMarketingAuth";
import {
  PUBLIC_INTEGRATIONS,
  PUBLIC_INTEGRATIONS_ATTRIBUTION,
  PUBLIC_INTEGRATIONS_COMING_SOON,
  PUBLIC_INTEGRATIONS_INTRO,
  TAGLINE,
} from "@/lib/marketingCopy";

const ease = [0.16, 1, 0.3, 1];
const fade = {
  hidden: { opacity: 0, y: 18 },
  show: (i = 0) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.65, ease, delay: i * 0.06 },
  }),
};

export default function PublicIntegrations() {
  const { authed, enter } = useMarketingAuth();

  useEffect(() => {
    window.scrollTo(0, 0);
  }, []);

  return (
    <div className="min-h-screen overflow-x-hidden bg-helm-cream text-helm-navy">
      <MarketingNav authed={authed} onEnter={enter} active="/integrations" />

      <main>
        <section className="px-6 pb-12 pt-36 md:pb-16 md:pt-44">
          <div className="mx-auto max-w-3xl">
            <motion.p
              variants={fade}
              initial="hidden"
              animate="show"
              custom={0}
              className="font-mono text-xs uppercase tracking-[0.3em] text-helm-slate"
            >
              Integrations
            </motion.p>
            <motion.h1
              variants={fade}
              initial="hidden"
              animate="show"
              custom={1}
              className="font-display mt-8 text-5xl font-medium leading-[1.05] tracking-[-0.03em] md:text-6xl"
            >
              Connected where it counts
            </motion.h1>
            <motion.p
              variants={fade}
              initial="hidden"
              animate="show"
              custom={2}
              className="mt-6 max-w-2xl text-lg leading-relaxed text-helm-slate"
            >
              {PUBLIC_INTEGRATIONS_INTRO}
            </motion.p>
          </div>
        </section>

        <section className="border-t border-helm-navy/[0.05] px-6 py-16 md:py-20">
          <div className="mx-auto grid max-w-6xl gap-px bg-helm-navy/[0.06] sm:grid-cols-2 lg:grid-cols-3">
            {PUBLIC_INTEGRATIONS.map((item, i) => (
              <motion.article
                key={item.id}
                variants={fade}
                initial="hidden"
                whileInView="show"
                viewport={{ once: true, margin: "-40px" }}
                custom={i}
                className="flex flex-col bg-helm-cream p-7 md:p-8"
                data-testid={`public-integration-${item.id}`}
              >
                <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-helm-slate">
                  {item.category}
                </p>
                <h2 className="font-display mt-4 text-2xl font-medium tracking-tight text-helm-navy">
                  {item.name}
                </h2>
                <p className="mt-4 flex-1 text-sm leading-relaxed text-helm-slate">
                  {item.description}
                </p>
                <p className="mt-5 font-mono text-[11px] uppercase tracking-[0.16em] text-helm-gold">
                  {item.feeds}
                </p>
                {item.scope ? (
                  <p className="mt-3 border-l border-helm-navy/15 pl-3 text-xs leading-relaxed text-helm-slate/90">
                    {item.scope}
                  </p>
                ) : null}
              </motion.article>
            ))}
          </div>
          <p className="mx-auto mt-10 max-w-3xl text-center text-[11px] leading-relaxed text-helm-slate/80">
            {PUBLIC_INTEGRATIONS_ATTRIBUTION}
          </p>
        </section>

        <section className="border-t border-helm-navy/[0.05] px-6 py-16 md:py-20">
          <div className="mx-auto max-w-3xl">
            <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-helm-slate">
              Coming soon — not shipped
            </p>
            <h2 className="font-display mt-4 text-3xl font-medium tracking-tight text-helm-navy">
              Planned connections
            </h2>
            <p className="mt-3 text-sm leading-relaxed text-helm-slate">
              These appear in Trenston&apos;s internal catalog as future work. They are not available to connect and are not
              part of today&apos;s product.
            </p>
            <ul className="mt-8 space-y-4">
              {PUBLIC_INTEGRATIONS_COMING_SOON.map((item) => (
                <li
                  key={item.id}
                  className="rounded-xl border border-dashed border-helm-navy/15 bg-helm-fg/[0.02] p-6"
                  data-testid={`public-integration-soon-${item.id}`}
                >
                  <div className="flex flex-wrap items-center gap-3">
                    <h3 className="text-base font-medium text-helm-navy">{item.name}</h3>
                    <span className="rounded-full border border-helm-navy/20 px-2 py-0.5 font-mono text-[10px] uppercase tracking-[0.16em] text-helm-slate">
                      Coming soon
                    </span>
                  </div>
                  <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.18em] text-helm-slate">{item.category}</p>
                  <p className="mt-3 text-sm leading-relaxed text-helm-slate">{item.description}</p>
                </li>
              ))}
            </ul>
          </div>
        </section>

        <section className="border-t border-helm-navy/[0.05] px-6 py-24">
          <div className="mx-auto max-w-2xl text-center">
            <div className="mx-auto mb-8 h-px w-10 bg-helm-gold" aria-hidden />
            <p className="font-display text-3xl font-medium leading-tight tracking-tight text-helm-navy md:text-4xl">
              {TAGLINE}
            </p>
            <p className="mt-4 text-sm text-helm-slate">
              Connect when it helps. Manual entry stays available everywhere else.
            </p>
            <button
              type="button"
              onClick={enter}
              className="mt-10 group inline-flex items-center gap-2 rounded-md bg-helm-cream px-6 py-3 font-medium text-helm-navy transition-colors hover:bg-helm-gold focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-helm-gold"
            >
              {authed ? "Open your cockpit" : "Get started"}
              <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
            </button>
            <p className="mt-6 flex flex-wrap items-center justify-center gap-x-5 gap-y-1 text-sm text-helm-slate">
              <Link to="/pricing" className="hover:text-helm-navy transition-colors">
                View pricing
              </Link>
              <Link to="/features" className="hover:text-helm-navy transition-colors">
                Features
              </Link>
              <Link to="/security" className="hover:text-helm-navy transition-colors">
                Security
              </Link>
              <Link to="/changelog" className="hover:text-helm-navy transition-colors">
                Changelog
              </Link>
            </p>
          </div>
        </section>
      </main>

      <MarketingFooter />
    </div>
  );
}
