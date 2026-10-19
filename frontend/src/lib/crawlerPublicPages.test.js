/**
 * @jest-environment node
 */
import { execFileSync } from "child_process";
import { readFileSync } from "fs";
import { join } from "path";

const frontendRoot = join(__dirname, "../..");

// Run in real Node (the module uses import.meta, which Jest cannot parse).
function body(path) {
  const code = `import("./scripts/staticPageText.mjs").then((m) => process.stdout.write(m.staticBodyFor(${JSON.stringify(path)}, { title: "T", description: "D" })))`;
  return execFileSync("node", ["-e", code], { cwd: frontendRoot, encoding: "utf8" });
}

describe("public pages show real text without JavaScript", () => {
  test("security prerender carries the data-exit and AI disclosure text", () => {
    const html = body("/security");
    expect(html).toContain("Your data, your exit");
    expect(html).toContain("Google Cloud Document AI");
    expect(html).toContain("not used to train");
    expect(html.length).toBeGreaterThan(4000);
  });

  test("privacy and terms prerender come from the page source", () => {
    const privacy = body("/privacy");
    expect(privacy).toContain("AI processing");
    expect(privacy).toContain("Retention &amp; deletion");
    expect(privacy).toContain("Limited Use");
    expect(privacy).toContain("Google API Services User Data Policy");
    const terms = body("/terms");
    expect(terms).toContain("BGC, Taguig, Philippines");
  });

  test("prerender script wires every public page through the static body", () => {
    const src = readFileSync(join(frontendRoot, "scripts/prerender-marketing.mjs"), "utf8");
    expect(src).toContain("staticBodyFor");
    expect(src).toContain("syncSitemapToBuild");
    expect(src).toContain("injectHomeFaqJsonLd");
  });

  test("homepage and features prerender carry real marketing copy", () => {
    const home = body("/");
    expect(home).toContain("Run your business");
    expect(home).toContain("Decision Center");
    expect(home.length).toBeGreaterThan(800);
    const features = body("/features");
    expect(features).toContain("Briefing");
    expect(features).toContain("Ask Trenston");
    expect(features.length).toBeGreaterThan(800);
  });

  test("robots disallows app and auth shells; allows marketing", () => {
    const robots = readFileSync(join(frontendRoot, "public/robots.txt"), "utf8");
    expect(robots).toContain("Allow: /");
    expect(robots).toContain("Disallow: /app");
    expect(robots).toContain("Disallow: /app/");
    expect(robots).toContain("Disallow: /login");
    expect(robots).toContain("Disallow: /sign-up");
    expect(robots).toContain("Sitemap: https://www.trenston.com/sitemap.xml");
  });

  test("prerender writes noindex shells for login, sign-up, app, payment, unsubscribe, and 404", () => {
    const src = readFileSync(join(frontendRoot, "scripts/prerender-marketing.mjs"), "utf8");
    expect(src).toContain("writeNoindexShells");
    expect(src).toContain('path: "/login"');
    expect(src).toContain('path: "/sign-up"');
    expect(src).toContain('path: "/app"');
    expect(src).toContain('path: "/payment"');
    expect(src).toContain('path: "/unsubscribe"');
    expect(src).toContain("404.html");
    expect(src).toContain("notFoundHtml");
    expect(src).toContain("noindex, nofollow");
  });

  test("vercel sends X-Robots-Tag noindex for auth, app, and unsubscribe; no homepage catch-all", () => {
    const vercel = JSON.parse(readFileSync(join(frontendRoot, "vercel.json"), "utf8"));
    expect(vercel.trailingSlash).toBe(false);
    const sources = (vercel.headers || []).map((h) => h.source);
    for (const path of ["/login", "/sign-up", "/app", "/app/(.*)", "/payment", "/unsubscribe"]) {
      expect(sources).toContain(path);
    }
    const appHeader = (vercel.headers || []).find((h) => h.source === "/app/(.*)");
    expect(appHeader.headers.some((h) => h.key === "X-Robots-Tag" && h.value.includes("noindex"))).toBe(true);
    const rewrites = (vercel.rewrites || []).map((r) => r.destination);
    expect(rewrites).toContain("/app/index.html");
    expect(rewrites).toContain("/login/index.html");
    // Soft-404 fix: unknown paths must not rewrite to the marketing homepage.
    expect(rewrites).not.toContain("/index.html");
    const redirects = vercel.redirects || [];
    expect(redirects.some((r) => r.source === "/blog" && r.destination === "/changelog" && r.permanent)).toBe(true);
  });

  test("home FAQ questions are interrogatives for FAQPage rich results", () => {
    const src = readFileSync(join(frontendRoot, "src/lib/marketingCopy.js"), "utf8");
    expect(src).toMatch(/q:\s*"How does billing and cancellation work\?"/);
    expect(src).toMatch(/q:\s*"How does Trenston keep my company data secure\?"/);
    expect(src).not.toMatch(/q:\s*"Billing & cancellation"/);
  });
});
