/**
 * Marketing design primitives — black / navy / white editorial system,
 * modelled on BlackRock.com's patterns: flat black and white bands, ruled
 * text columns, arrow text-links, square buttons, no gradients or glows.
 * Styling + motion lives in index.css under `.mk-*`. Every public page renders
 * inside <MkPage>, which opts framer-motion into reduced-motion preferences.
 */
import { useState } from "react";
import { Link } from "react-router-dom";
import { AnimatePresence, MotionConfig, motion } from "motion/react";
import { ArrowDownRight, ArrowRight, Plus } from "lucide-react";
import MarketingNav from "@/components/marketing/MarketingNav";
import MarketingFooter from "@/components/marketing/MarketingFooter";
import { cn } from "@/lib/utils";

export const ease = [0.16, 1, 0.3, 1];

/** Display type: medium weight, tight but not crushed. */
export const DISPLAY = "font-medium tracking-[-0.03em]";

export const fadeUp = {
  hidden: { opacity: 0, y: 20 },
  show: (i = 0) => ({ opacity: 1, y: 0, transition: { duration: 0.7, ease, delay: i * 0.07 } }),
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
export function MkButton({ to, href, onClick, variant = "dark", size, arrow = true, className, children, ...rest }) {
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
        "text-xs font-semibold uppercase tracking-[0.16em]",
        dark ? "text-mk-gray-dark" : "text-mk-navy",
        className,
      )}
    >
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
export function SplitHeadline({ lines, className, as = "h1", delay = 0.05 }) {
  const Tag = as;
  return (
    <Tag className={className}>
      {lines.map((line, i) => (
        <span key={i} className="block overflow-hidden pb-[0.1em]">
          <motion.span
            className="block"
            initial={{ y: "100%" }}
            animate={{ y: 0 }}
            transition={{ duration: 0.9, ease, delay: delay + i * 0.1 }}
          >
            {line}
          </motion.span>
        </span>
      ))}
    </Tag>
  );
}

/**
 * Black page header for inner pages. Optional `toc` renders an
 * "On this page" jump list on the right (anchors to section ids); `aside`
 * renders arbitrary content there instead.
 */
export function PageHero({ eyebrow, lines, sub, children, toc, aside, size = "lg", className }) {
  return (
    <section className={cn("bg-mk-black text-white", className)}>
      <div className="mx-auto max-w-7xl px-6 pb-16 pt-32 md:pb-20 md:pt-40">
        <div className={cn("grid gap-14", (toc || aside) && "lg:grid-cols-[1.5fr_1fr] lg:items-end")}>
          <div>
            {eyebrow && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.6 }}>
                <Eyebrow dark>{eyebrow}</Eyebrow>
              </motion.div>
            )}
            <SplitHeadline
              lines={lines}
              className={cn(
                "mt-6 leading-[1.04]",
                size === "md" ? "text-4xl sm:text-5xl lg:text-[3.5rem]" : "text-5xl sm:text-6xl lg:text-[4.5rem]",
                DISPLAY,
              )}
            />
            {sub && (
              <motion.p
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.7, ease, delay: 0.35 }}
                className="mt-8 max-w-2xl text-lg leading-relaxed text-mk-gray-dark"
              >
                {sub}
              </motion.p>
            )}
            {children && (
              <motion.div
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.7, ease, delay: 0.45 }}
                className="mt-10"
              >
                {children}
              </motion.div>
            )}
          </div>
          {aside && !toc && (
            <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.8, ease, delay: 0.4 }}>
              {aside}
            </motion.div>
          )}
          {toc && (
            <motion.nav
              aria-label="On this page"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.7, delay: 0.5 }}
            >
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-mk-gray-dark">On this page</p>
              <ul className="mt-4 border-t border-white/25">
                {toc.map((t) => (
                  <li key={t.id} className="border-b border-white/25">
                    <a
                      href={`#${t.id}`}
                      className="group flex items-center justify-between py-3.5 text-[0.9375rem] text-white/85 transition-colors hover:text-white"
                    >
                      <span className="mk-title-line">{t.label}</span>
                      <ArrowDownRight className="h-4 w-4 transition-transform duration-300 group-hover:translate-x-0.5 group-hover:translate-y-0.5" aria-hidden />
                    </a>
                  </li>
                ))}
              </ul>
            </motion.nav>
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
            "mt-4 text-4xl leading-[1.05] md:text-[3.25rem]",
            DISPLAY,
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

/**
 * Ruled text column (BlackRock-style card): hairline on top, small icon,
 * title, body, optional children. The rule thickens on hover.
 */
export function RuledItem({ icon: Icon, index, title, body, children, dark = false, i = 0, className }) {
  return (
    <Reveal i={i} className={cn("mk-item group", dark && "mk-item-dark", className)}>
      <div className="flex items-start justify-between gap-4">
        {Icon ? <Icon className={cn("h-6 w-6", dark ? "text-white" : "text-mk-navy")} strokeWidth={1.5} aria-hidden /> : <span />}
        {index != null && (
          <span className={cn("font-mono text-xs", dark ? "text-mk-gray-dark" : "text-mk-gray")}>
            {String(index).padStart(2, "0")}
          </span>
        )}
      </div>
      <h3 className={cn("mt-6 text-xl font-semibold leading-snug tracking-tight", dark ? "text-white" : "text-mk-black")}>
        {title}
      </h3>
      {body && <p className={cn("mt-3 leading-relaxed", dark ? "text-mk-gray-dark" : "text-mk-gray")}>{body}</p>}
      {children}
    </Reveal>
  );
}

/** Closing black call-to-action band. */
export function CtaBand({ title, sub, authed, onEnter, secondary }) {
  return (
    <section className="bg-mk-black text-white">
      <div className="mx-auto max-w-7xl px-6 py-24 md:py-28">
        <Reveal className="grid gap-10 lg:grid-cols-[1.4fr_1fr] lg:items-end">
          <h2 className={cn("text-5xl leading-[1.02] md:text-6xl", DISPLAY)}>{title}</h2>
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
    <div className={cn("border-t", dark ? "border-white/25" : "border-mk-black")}>
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
                  dark ? "text-white" : "text-mk-black hover:text-mk-navy",
                )}
              >
                {item.q}
                <span
                  className={cn(
                    "flex h-9 w-9 shrink-0 items-center justify-center border transition-colors duration-300",
                    isOpen
                      ? "border-mk-black bg-mk-black text-white"
                      : dark
                        ? "border-white/40 text-white"
                        : "border-mk-line text-mk-black group-hover:border-mk-black",
                  )}
                  aria-hidden
                >
                  <Plus className={cn("h-4 w-4 transition-transform duration-300", isOpen && "rotate-45")} />
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
                  transition={{ duration: 0.4, ease }}
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
      transition={{ duration: 1.2, ease }}
    />
  );
}

/** Flat mist panel that frames a product visual like an editorial image. */
export function VisualPanel({ children, className }) {
  return (
    <div className={cn("flex items-center justify-center bg-mk-mist p-6 sm:p-10 lg:p-12", className)}>
      <div className="w-full">{children}</div>
    </div>
  );
}
