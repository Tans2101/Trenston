/**
 * User-facing copy should not use em dashes in prose; they read as
 * machine-written. A lone "—" used as an empty-value placeholder in a table
 * cell is fine. Comments are ignored (only string/JSX text nodes are checked).
 */
const fs = require("fs");
const path = require("path");
const { parse } = require("@babel/parser");
const traverse = require("@babel/traverse").default;

const SRC = path.join(__dirname, "..");
const EM = "—";

function sourceFiles(dir) {
  const out = [];
  for (const name of fs.readdirSync(dir)) {
    const p = path.join(dir, name);
    if (fs.statSync(p).isDirectory()) {
      out.push(...sourceFiles(p));
    } else if (/\.(jsx?|mjs)$/.test(name) && !/\.test\./.test(name)) {
      out.push(p);
    }
  }
  return out;
}

function proseEmDashes(file) {
  const code = fs.readFileSync(file, "utf8");
  if (!code.includes(EM)) return [];
  const ast = parse(code, { sourceType: "module", plugins: ["jsx"] });
  const hits = [];
  traverse(ast, {
    enter({ node }) {
      let value = null;
      if (node.type === "StringLiteral" || node.type === "JSXText") value = node.value;
      else if (node.type === "TemplateElement") value = node.value.cooked ?? node.value.raw;
      if (value && value.includes(EM) && value.trim() !== EM) {
        hits.push(`${path.relative(SRC, file)}:${node.loc.start.line} ${value.trim().slice(0, 80)}`);
      }
    },
  });
  return hits;
}

test("no em dashes in user-facing prose", () => {
  const hits = sourceFiles(SRC).flatMap(proseEmDashes);
  expect(hits).toEqual([]);
});

function jsonStrings(value, out = []) {
  if (typeof value === "string") out.push(value);
  else if (Array.isArray(value)) value.forEach((v) => jsonStrings(v, out));
  else if (value && typeof value === "object") Object.values(value).forEach((v) => jsonStrings(v, out));
  return out;
}

test("no em dashes in user-facing JSON copy (changelog)", () => {
  const data = JSON.parse(fs.readFileSync(path.join(SRC, "lib", "changelog.json"), "utf8"));
  const hits = jsonStrings(data).filter((t) => t.includes(EM) && t.trim() !== EM);
  expect(hits.map((t) => t.slice(0, 80))).toEqual([]);
});
