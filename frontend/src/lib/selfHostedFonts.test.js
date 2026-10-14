/** Guardrail: Trenston must not load fonts from Google's CDN (GDPR / privacy). */
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "../..");
const PUBLIC = path.join(ROOT, "public");
const INDEX = path.join(ROOT, "index.html");
const FONTS_CSS = path.join(PUBLIC, "fonts/fonts.css");
const FONTS_DIR = path.join(PUBLIC, "fonts");

const CDN_RE = /https?:\/\/fonts\.(googleapis|gstatic)\.com/i;

describe("self-hosted fonts", () => {
  test("index.html has no Google Fonts CDN links or preconnects", () => {
    const html = fs.readFileSync(INDEX, "utf8");
    expect(html).not.toMatch(CDN_RE);
    expect(html).toContain('href="/fonts/fonts.css"');
    expect(html).toContain('href="/fonts/inter-latin.woff2"');
    expect(html).not.toMatch(/dm-sans|dm-mono|hedvig/i);
  });

  test("fonts.css declares local faces with font-display swap", () => {
    const css = fs.readFileSync(FONTS_CSS, "utf8");
    expect(css).not.toMatch(CDN_RE);
    expect(css).toMatch(/font-family:\s*'Inter'/);
    expect(css).toMatch(/font-family:\s*'JetBrains Mono'/);
    expect(css).toMatch(/font-display:\s*swap/);
    expect(css).toMatch(/font-weight:\s*100 900/);
    expect(css).toContain("url('/fonts/inter-latin.woff2')");
    // Peso and other currency signs live in the latin-ext file.
    expect(css).toContain("url('/fonts/inter-latin-ext.woff2')");
  });

  test("required woff2 files exist on disk", () => {
    const required = [
      "inter-latin.woff2",
      "inter-latin-ext.woff2",
      "inter-latin-italic.woff2",
      "jetbrains-mono-latin.woff2",
    ];
    for (const name of required) {
      const full = path.join(FONTS_DIR, name);
      expect(fs.existsSync(full)).toBe(true);
      expect(fs.statSync(full).size).toBeGreaterThan(1000);
    }
  });
});
