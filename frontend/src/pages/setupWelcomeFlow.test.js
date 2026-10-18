/**
 * The demo-first screens sit in front of company setup, so a crash there
 * blocks every brand-new owner. Static scope analysis catches undeclared
 * identifiers without a render harness, and a few source checks pin the
 * gating rules in AppLayout.
 */
const fs = require("fs");
const path = require("path");
const { parse } = require("@babel/parser");
const traverse = require("@babel/traverse").default;
const globals = require("globals");

const KNOWN_GLOBALS = new Set([
  ...Object.keys(globals.browser),
  ...Object.keys(globals.es2021),
  "React",
]);

const read = (rel) => fs.readFileSync(path.join(__dirname, rel), "utf8");

function findUndeclaredIdentifiers(rel) {
  const ast = parse(read(rel), { sourceType: "module", plugins: ["jsx"] });
  const undeclared = [];
  traverse(ast, {
    ReferencedIdentifier(refPath) {
      const name = refPath.node.name;
      if (KNOWN_GLOBALS.has(name)) return;
      if (refPath.scope.hasBinding(name)) return;
      undeclared.push({ name, line: refPath.node.loc.start.line });
    },
  });
  return undeclared;
}

describe("demo-first setup flow", () => {
  it.each([
    "SetupWelcome.jsx",
    "../components/DemoBanner.jsx",
    "../components/AppLayout.jsx",
  ])("%s has no references to undeclared identifiers", (file) => {
    expect(findUndeclaredIdentifiers(file)).toEqual([]);
  });

  it("opening the demo asks the server for the pre-setup demo template", () => {
    expect(read("SetupWelcome.jsx")).toMatch(/template: "demo"/);
  });

  it("leaving the demo clears the sample data on the server", () => {
    expect(read("../components/DemoBanner.jsx")).toMatch(/\/workspace\/clear-sample/);
  });

  it("AppLayout keeps the demo out of the company-setup gate and shows the welcome choice first", () => {
    const src = read("../components/AppLayout.jsx");
    expect(src).toMatch(/company_setup_done === false && !inDemo/);
    expect(src).toMatch(/!skipWelcome && !company\?\.demo_seen/);
    expect(src).toMatch(/\{inDemo && <DemoBanner \/>\}/);
  });

  it("DemoBanner follows the live sidebar width (collapsed rail included)", () => {
    expect(read("../components/DemoBanner.jsx")).toMatch(/lg:pl-\[var\(--sidebar-w\)\]/);
  });

  it("Onboarding template choose guards against double-submit like departments", () => {
    const src = read("Onboarding.jsx");
    const chooseIdx = src.indexOf("const choose = async (template)");
    expect(chooseIdx).toBeGreaterThan(-1);
    expect(src.slice(chooseIdx, chooseIdx + 200)).toMatch(/if \(busy\) return/);
  });
});
