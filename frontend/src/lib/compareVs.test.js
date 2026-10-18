/**
 * Guardrails for the one-to-one comparison pages. These pages name other
 * companies' products, so the copy is kept to what is safe to publish:
 * quotes with a source and date, no prices, no "worse than" or missing-feature
 * claims, a trademark note, and an honest "when the other tool is better".
 */
import content from "./compareVs.json";
import story from "./homeStory.json";

const OFFICIAL_HOSTS = ["www.microsoft.com", "learn.microsoft.com", "workspace.google.com", "www.notion.com"];
const BANNED = [
  /\$\s?\d/, /\bper (month|user|seat)\b/i, /\bfree plan\b/i, /\bcheaper\b/i, /\bexpensive\b/i,
  /\bworse\b/i, /\bworst\b/i, /\binferior\b/i, /\bbetter than\b/i, /\bbeats?\b/i, /\bkills?\b/i,
  /\bcannot\b/i, /\bcan't\b/i, /\bdoes not (have|support|offer)\b/i, /\black(s|ing)?\b/i,
  /\bunlike\b/i, /\bslow\b/i, /\binsecure\b/i, /\bbroken\b/i, /\bbest\b/i, /\b#1\b/,
];

function allStrings(v, out = []) {
  if (typeof v === "string") out.push(v);
  else if (Array.isArray(v)) v.forEach((x) => allStrings(x, out));
  else if (v && typeof v === "object") Object.values(v).forEach((x) => allStrings(x, out));
  return out;
}

describe("comparison pages", () => {
  test("there are three pages with unique slugs", () => {
    const slugs = content.pages.map((p) => p.slug);
    expect(slugs).toEqual(["excel-google-sheets", "power-bi", "notion"]);
  });

  test("every page quotes an official source with a link", () => {
    for (const p of content.pages) {
      expect(p.sources.length).toBeGreaterThan(0);
      for (const s of p.sources) {
        const u = new URL(s.url);
        expect(u.protocol).toBe("https:");
        expect(OFFICIAL_HOSTS).toContain(u.hostname);
        expect(s.quote.split(/\s+/).length).toBeLessThanOrEqual(25);
        expect(s.label).toBeTruthy();
      }
    }
  });

  test("every page says when the other tool is the better choice", () => {
    for (const p of content.pages) {
      expect(p.useToolWhen.length).toBeGreaterThanOrEqual(3);
      expect(p.useTrenstonWhen.length).toBeGreaterThanOrEqual(3);
      expect(p.together).toBeTruthy();
    }
  });

  test("carries an as-of date, trademark notice and non-affiliation line", () => {
    expect(content.asOf).toMatch(/2026/);
    expect(content.trademarks).toMatch(/trademarks/i);
    expect(content.trademarks).toMatch(/not affiliated with/i);
    expect(content.notAdvice).toMatch(/not legal/i);
    expect(content.notAdvice).toMatch(/contact@trenston\.com/);
  });

  test("copy has no prices, rankings or missing-feature claims outside the quotes", () => {
    const quotes = new Set(content.pages.flatMap((p) => p.sources.map((s) => s.quote)));
    const strings = allStrings({ ...content, pages: content.pages.map((p) => ({ ...p, sources: [] })) });
    for (const text of strings) {
      if (quotes.has(text)) continue;
      for (const re of BANNED) {
        expect({ text, re: String(re), hit: re.test(text) }).toMatchObject({ hit: false });
      }
    }
  });

  test("copy has no em dashes", () => {
    for (const text of [...allStrings(content), ...allStrings(story)]) {
      expect(text).not.toContain("—");
    }
  });

  test("homepage problem and why-us sections are filled in", () => {
    expect(story.problem.items.length).toBeGreaterThanOrEqual(3);
    expect(story.whyUs.items.length).toBe(4);
  });
});
