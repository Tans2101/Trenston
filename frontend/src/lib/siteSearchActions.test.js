/** ⌘K site search covers public marketing pages (except home and /integrations). */
import { SITE_SEARCH_ACTIONS } from "./siteSearchActions";
import { SEO_PAGES } from "./seoPages";

/** Public marketing routes intentionally left out of in-app ⌘K. */
const SITE_SEARCH_EXCLUDED = new Set(["/", "/integrations"]);

describe("quick nav site search pages", () => {
  test("includes About, Features, and other public marketing routes", () => {
    const pathTos = SITE_SEARCH_ACTIONS.filter((a) => a.to.startsWith("/")).map((a) => a.to).sort();
    expect(pathTos).toEqual(
      [
        "/about",
        "/changelog",
        "/compare",
        "/features",
        "/help",
        "/pricing",
        "/privacy",
        "/refunds",
        "/security",
        "/status",
        "/terms",
      ].sort(),
    );
    expect(SITE_SEARCH_ACTIONS.find((a) => a.id === "about")?.label).toBe("About");
    expect(SITE_SEARCH_ACTIONS.find((a) => a.id === "contact")?.to).toMatch(/^mailto:/);
  });

  test("does not list the public Integrations marketing page", () => {
    expect(SITE_SEARCH_ACTIONS.some((a) => a.to === "/integrations")).toBe(false);
  });

  test("every SEO marketing page except excluded ones is searchable", () => {
    const searchable = new Set(SITE_SEARCH_ACTIONS.map((a) => a.to));
    for (const path of Object.keys(SEO_PAGES)) {
      if (SITE_SEARCH_EXCLUDED.has(path)) continue;
      expect(searchable.has(path)).toBe(true);
    }
  });
});
