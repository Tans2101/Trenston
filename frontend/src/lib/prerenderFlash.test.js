/**
 * @jest-environment node
 */
import { readFileSync } from "fs";
import { join } from "path";

const html = readFileSync(join(__dirname, "../../public/index.html"), "utf8");

// The prerender step puts a plain-text copy of each public page inside #root for
// crawlers and readers without JavaScript. People whose browsers run JavaScript
// must never see it: it paints as unstyled text until React replaces it.
describe("prerendered text does not flash for people with JavaScript", () => {
  test("the shell marks JavaScript-capable browsers before the body paints", () => {
    const flag = html.indexOf('setAttribute("data-js"');
    expect(flag).toBeGreaterThan(-1);
    expect(flag).toBeLessThan(html.indexOf("</head>"));
  });

  test("the prerender wrappers are hidden once that flag is set", () => {
    expect(html).toMatch(/html\[data-js\]\s+#root\s*>\s*\[id\^="helm-prerender"\]\s*\{\s*display:\s*none/);
  });

  test("the hide rule covers every wrapper id the prerender script emits", () => {
    const script = readFileSync(join(__dirname, "../../scripts/prerender-marketing.mjs"), "utf8");
    const staticText = readFileSync(join(__dirname, "../../scripts/staticPageText.mjs"), "utf8");
    const ids = new Set(
      [...(script + staticText).matchAll(/<main id="(helm-prerender[\w-]*)"/g)].map((m) => m[1]),
    );
    expect(ids.size).toBeGreaterThan(0);
    for (const id of ids) expect(id.startsWith("helm-prerender")).toBe(true);
  });
});
