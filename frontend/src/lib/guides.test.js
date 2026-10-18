/**
 * Guardrails for the founder guides: they must be accurate, free of em dashes,
 * wired into SEO, and the worked runway example must add up.
 */
import content from "./guidesContent.json";
import { SEO_PAGES } from "./seoPages";

const text = (g) =>
  [g.intro, ...g.sections.flatMap((s) => [s.heading, ...(s.paragraphs || []), ...(s.bullets || [])]),
    g.trenston.heading, ...g.trenston.paragraphs].join(" ");

describe("guides", () => {
  test("every guide has an SEO entry and a hub entry", () => {
    expect(content.guides.length).toBeGreaterThanOrEqual(2);
    expect(SEO_PAGES["/guides"]).toBeTruthy();
    for (const g of content.guides) {
      expect(SEO_PAGES[`/guides/${g.slug}`]).toBeTruthy();
      expect(g.description.length).toBeLessThanOrEqual(200);
      expect(g.sections.length).toBeGreaterThanOrEqual(5);
      expect(g.datePublished).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    }
  });

  test("the runway example adds up", () => {
    const g = content.guides.find((x) => x.slug === "how-to-track-runway-as-a-founder");
    const { cash, monthlyExpenses, monthlyRevenue } = g.example;
    const burn = monthlyExpenses - monthlyRevenue;
    const months = cash / burn;
    const t = text(g);
    expect(t).toContain(`$${cash.toLocaleString("en-US")}`);
    expect(t).toContain(`$${burn.toLocaleString("en-US")} a month`);
    expect(t).toContain(`${months} months`);
    // Spending up by $10,000 with nothing else changing.
    expect(t).toContain(`${(cash / (burn + 10000)).toFixed(1)} months`);
  });

  test("no em dashes and no guarantees", () => {
    for (const g of content.guides) {
      const t = text(g);
      expect(t).not.toContain("—");
      expect(t).not.toMatch(/\bguarantee/i);
    }
  });
});
