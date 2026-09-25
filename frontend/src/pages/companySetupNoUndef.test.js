/**
 * Regression: CompanySetup.jsx must not reference an identifier that was
 * never declared or imported (e.g. `needsDisplayName` at the "From your
 * sign-in" hint) — a plain `ReferenceError` there crashed every brand-new
 * user's first render of Step 0 via the ErrorBoundary fallback, since
 * WorkspaceGate's create() lands a fresh workspace straight on CompanySetup.
 *
 * Static scope analysis (babel) catches this whole bug class without
 * needing a full component-render harness.
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

function findUndeclaredIdentifiers(filePath) {
  const code = fs.readFileSync(filePath, "utf8");
  const ast = parse(code, { sourceType: "module", plugins: ["jsx"] });
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

test("CompanySetup.jsx has no references to undeclared identifiers", () => {
  const filePath = path.join(__dirname, "CompanySetup.jsx");
  expect(findUndeclaredIdentifiers(filePath)).toEqual([]);
});
