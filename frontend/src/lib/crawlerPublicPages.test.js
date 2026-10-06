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
    expect(robots).toContain("Disallow: /app/");
    expect(robots).toContain("Disallow: /login");
    expect(robots).toContain("Disallow: /sign-up");
    expect(robots).toContain("Sitemap: https://www.trenston.com/sitemap.xml");
  });
});
