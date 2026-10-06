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
  });
});
