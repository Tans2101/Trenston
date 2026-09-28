/**
 * Marketing design primitives — black / navy / white editorial system.
 * Styling + motion lives in index.css under `.mk-*`; these components only
 * compose it. Every public page renders inside <MkPage>, which also opts all
 * framer-motion animations into the user's reduced-motion preference.
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import { AnimatePresence, MotionConfig, motion } from "motion/react";
import { ArrowRight, Plus } from "lucide-react";
import MarketingNav from "@/components/marketing/MarketingNav";
import MarketingFooter from "@/components/marketing/MarketingFooter";
import { cn } from "@/lib/utils";

export const ease = [0.16, 1, 0.3, 1];

export const fadeUp = {
  hidden: { opacity: 0, y: 28 },
  show: (i = 0) => ({ opacity: 1, y: 0, transition: { duration: 0.8, ease, delay: i * 0.08 } }),
};

/** Page shell: white canvas, marketing nav + footer, reduced-motion aware. */
export function MkPage({ authed, onEnter, active, children, className }) {
  return (
    <MotionConfig reducedMotion="user">
      <div className={cn("mk min-h-screen overflow-x-hidden bg-white text-mk-black antialiased", className)}>
        <MarketingNav authed={authed} onEnter={onEnter} active={active} />
        <main>{children}</main>
        <MarketingFooter />
      </div>
    </MotionConfig>
  );
}

/** Button / link styled as a sweep-fill button. */
export function MkButton({
  to,
  href,
  onClick,
  variant = "dark",
  size,
  arrow = true,
  className,
  children,
  ...rest
}) {
  const cls = cn("mk-btn", `mk-btn-${variant}`, size === "sm" && "mk-btn-sm", className);
  const inner = (
    <>
      <span>{children}</span>
      {arrow && <ArrowRight className="mk-arrow h-4 w-4" aria-hidden />}
    </>
  );
  if (to) return <Link to={to} className={cls} onClick={onClick} {...rest}>{inner}</Link>;
  if (href) return <a href={href} className={cls} onClick={onClick} {...rest}>{inner}</a>;
  return <button type="button" className={cls} onClick={onClick} {...rest}>{inner}</button>;
}

/** Arrow text link with grow-underline. */
export function MkLink({ to, href, children, className, ...rest }) {
  const cls = cn("mk-link text-sm", className);
  const inner = (
    <>
      {children}
      <ArrowRight className="mk-arrow h-4 w-4" aria-hidden />
    </>
  );
  if (to) return <Link to={to} className={cls} {...rest}>{inner}</Link>;
  return <a href={href} className={cls} {...rest}>{inner}</a>;
}

export function Eyebrow({ children, dark = false, className }) {
  return (
    <p
      className={cn(
        "flex items-center gap-3 text-xs font-semibold uppercase tracking-[0.18em]",
        dark ? "text-mk-gray-dark" : "text-mk-navy",
        className,
      )}
    >
      <span className={cn("h-px w-8", dark ? "bg-mk-sky" : "bg-mk-navy")} aria-hidden />
      {children}
    </p>
  );
}

/** Scroll-reveal wrapper. */
export function Reveal({ children, className, i = 0, as = "div", ...rest }) {
  const Comp = motion[as] || motion.div;
  return (
    <Comp
      variants={fadeUp}
      custom={i}
      initial="hidden"
      whileInView="show"
      viewport={{ once: true, margin: "-60px" }}
      className={className}
      {...rest}
    >
      {children}
    </Comp>
  );
}

/** Headline whose lines rise out of a clipping mask, one after another. */
export function SplitHeadline({ lines, className, as = "h1", delay = 0.1 }) {
  const Tag = as;
  return (
    <Tag className={className}>
      {lines.map((line, i) => (
        <span key={i} className="block overflow-hidden pb-[0.08em]">
          <motion.span
            className="block"
            initial={{ y: "105%" }}
            animate={{ y: 0 }}
            transition={{ duration: 1, ease, delay: delay + i * 0.12 }}
          >
            {line}
          </motion.span>
        </span>
      ))}
    </Tag>
  );
}

/** Animated backdrop for black bands: panning grid + drifting navy glow. */
export function DarkBackdrop() {
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
      <div className="mk-glow absolute -right-[10%] -top-[30%] h-[80vh] w-[80vh] rounded-full" />
      <div className="mk-grid absolute inset-0" />
    </div>
  );
}

/** Black page header used by every inner page. */
export function PageHero({ eyebrow, lines, sub, children, aside, className }) {
  return (
    <section className={cn("relative overflow-hidden bg-mk-black text-white", className)}>
      <DarkBackdrop />
      <div className="relative mx-auto max-w-7xl px-6 pb-20 pt-36 md:pb-28 md:pt-44">
        <div className={cn("grid gap-12", aside && "lg:grid-cols-[1.1fr_0.9fr] lg:items-end")}>
          <div>
            {eyebrow && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.6 }}>
                <Eyebrow dark>{eyebrow}</Eyebrow>
              </motion.div>
            )}
            <SplitHeadline
              lines={lines}
              className="mt-8 text-5xl font-semibold leading-[0.98] tracking-[-0.04em] sm:text-6xl lg:text-7xl"
            />
            {sub && (
              <motion.p
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.8, ease, delay: 0.45 }}
                className="mt-8 max-w-2xl text-lg leading-relaxed text-mk-gray-dark md:text-xl"
              >
                {sub}
              </motion.p>
            )}
            {children && (
              <motion.div
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.8, ease, delay: 0.6 }}
                className="mt-10"
              >
                {children}
              </motion.div>
            )}
          </div>
          {aside && (
            <motion.div
              initial={{ opacity: 0, y: 24 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.9, ease, delay: 0.5 }}
            >
              {aside}
            </motion.div>
          )}
        </div>
      </div>
    </section>
  );
}

/** Section heading block: eyebrow, large title, optional intro and action. */
export function SectionHeader({ eyebrow, title, intro, action, dark = false, className }) {
  return (
    <Reveal className={cn("flex flex-col gap-6 md:flex-row md:items-end md:justify-between", className)}>
      <div className="max-w-3xl">
        {eyebrow && <Eyebrow dark={dark}>{eyebrow}</Eyebrow>}
        <h2
          className={cn(
            "mt-5 text-4xl font-semibold leading-[1.02] tracking-[-0.035em] md:text-5xl",
            dark ? "text-white" : "text-mk-black",
          )}
        >
          {title}
        </h2>
        {intro && (
          <p className={cn("mt-5 max-w-2xl text-lg leading-relaxed", dark ? "text-mk-gray-dark" : "text-mk-gray")}>
            {intro}
          </p>
        )}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </Reveal>
  );
}

/** Infinite ticker. Items render twice so the -50% loop is seamless. */
export function Marquee({ items, className }) {
  const row = (hidden) =>
    items.map((item, i) => (
      <span
        key={`${hidden ? "b" : "a"}-${i}`}
        aria-hidden={hidden || undefined}
        className="flex shrink-0 items-center gap-10 pr-10 text-sm font-semibold uppercase tracking-[0.16em]"
      >
        {item}
        <span className="h-1.5 w-1.5 rotate-45 bg-current opacity-50" aria-hidden />
      </span>
    ));
  return (
    <div className={cn("mk-marquee", className)}>
      <div className="mk-marquee-track py-5">
        {row(false)}
        {row(true)}
      </div>
    </div>
  );
}

/** Closing black call-to-action band. */
export function CtaBand({ title, sub, authed, onEnter, secondary }) {
  return (
    <section className="relative overflow-hidden bg-mk-black text-white">
      <DarkBackdrop />
      <div className="relative mx-auto max-w-7xl px-6 py-24 md:py-32">
        <Reveal className="grid gap-10 lg:grid-cols-[1.4fr_1fr] lg:items-end">
          <h2 className="text-5xl font-semibold leading-[0.98] tracking-[-0.04em] md:text-7xl">{title}</h2>
          <div>
            {sub && <p className="text-lg leading-relaxed text-mk-gray-dark">{sub}</p>}
            <div className="mt-8 flex flex-wrap gap-3">
              <MkButton variant="light" onClick={onEnter} data-testid="footer-cta-btn">
                {authed ? "Open your cockpit" : "Get started free"}
              </MkButton>
              {secondary}
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}

/** Expandable FAQ list with animated height. */
export function MkAccordion({ items, idPrefix = "faq", dark = false }) {
  const [open, setOpen] = useState(0);
  return (
    <div className={cn("border-t", dark ? "border-white/15" : "border-mk-line")}>
      {items.map((item, i) => {
        const isOpen = open === i;
        return (
          <div key={item.q} className={cn("border-b", dark ? "border-white/15" : "border-mk-line")}>
            <h3>
              <button
                type="button"
                id={`${idPrefix}-trigger-${i}`}
                aria-expanded={isOpen}
                aria-controls={`${idPrefix}-panel-${i}`}
                onClick={() => setOpen(isOpen ? -1 : i)}
                className={cn(
                  "group flex w-full items-center justify-between gap-6 py-6 text-left text-lg font-semibold tracking-tight transition-colors md:text-xl",
                  dark ? "text-white hover:text-mk-sky" : "text-mk-black hover:text-mk-navy",
                )}
              >
                {item.q}
                <span
                  className={cn(
                    "flex h-9 w-9 shrink-0 items-center justify-center border transition-colors duration-500",
                    isOpen
                      ? "border-mk-navy bg-mk-navy text-white"
                      : dark
                        ? "border-white/30 text-white"
                        : "border-mk-line text-mk-black group-hover:border-mk-navy",
                  )}
                  aria-hidden
                >
                  <Plus className={cn("h-4 w-4 transition-transform duration-500", isOpen && "rotate-45")} />
                </span>
              </button>
            </h3>
            <AnimatePresence initial={false}>
              {isOpen && (
                <motion.div
                  id={`${idPrefix}-panel-${i}`}
                  role="region"
                  aria-labelledby={`${idPrefix}-trigger-${i}`}
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.45, ease }}
                  className="overflow-hidden"
                >
                  <div className="max-w-3xl pb-7">
                    <p className={cn("leading-relaxed", dark ? "text-mk-gray-dark" : "text-mk-gray")}>{item.a}</p>
                    {item.link ? (
                      <MkLink to={item.link.to} className={cn("mt-4", dark ? "text-white" : "text-mk-navy")}>
                        {item.link.label}
                      </MkLink>
                    ) : null}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        );
      })}
    </div>
  );
}

/** Horizontal rule that draws itself when scrolled into view. */
export function DrawLine({ className }) {
  return (
    <motion.div
      aria-hidden
      className={cn("h-px origin-left", className)}
      initial={{ scaleX: 0 }}
      whileInView={{ scaleX: 1 }}
      viewport={{ once: true, amount: 0 }}
      transition={{ duration: 1.4, ease }}
    />
  );
}
