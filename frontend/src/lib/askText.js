/**
 * Ask Trenston answers use a small slice of Markdown (paragraphs, bullet and
 * numbered lists, **bold**, *italic*, `code`). Parse it into plain blocks the
 * page renders as React elements, so nothing is injected as HTML.
 */

const BULLET_RE = /^\s*[-*•]\s+(.*)$/;
const NUMBERED_RE = /^\s*\d+[.)]\s+(.*)$/;
const HEADING_RE = /^\s*#{1,6}\s+(.*)$/;

/** Split answer text into { type: "p" | "ul" | "ol" | "h", ... } blocks. */
export function parseAskBlocks(text) {
  const blocks = [];
  let para = [];
  let list = null;
  const flushPara = () => {
    if (para.length) blocks.push({ type: "p", lines: para });
    para = [];
  };
  const flushList = () => {
    if (list) blocks.push(list);
    list = null;
  };
  for (const raw of String(text || "").replace(/\r\n/g, "\n").split("\n")) {
    const line = raw.trimEnd();
    if (!line.trim()) {
      flushPara();
      flushList();
      continue;
    }
    const heading = line.match(HEADING_RE);
    const bullet = line.match(BULLET_RE);
    const numbered = line.match(NUMBERED_RE);
    if (heading) {
      flushPara();
      flushList();
      blocks.push({ type: "h", text: heading[1] });
    } else if (bullet || numbered) {
      flushPara();
      const type = bullet ? "ul" : "ol";
      if (!list || list.type !== type) {
        flushList();
        list = { type, items: [] };
      }
      list.items.push((bullet || numbered)[1]);
    } else if (list && /^\s{2,}\S/.test(raw)) {
      // Indented continuation of the previous list item.
      list.items[list.items.length - 1] += ` ${line.trim()}`;
    } else {
      flushList();
      para.push(line);
    }
  }
  flushPara();
  flushList();
  return blocks;
}

const INLINE_RE = /(\*\*[^*\n]+\*\*|__[^_\n]+__|`[^`\n]+`|(?<![\w*])\*(?!\s)[^*\n]+?\*(?![\w*])|(?<![\w_])_(?!\s)[^_\n]+?_(?![\w_]))/g;

/** Split one line into [{ text, bold?, italic?, code? }] runs. */
export function parseAskInline(line) {
  const out = [];
  let last = 0;
  const src = String(line || "");
  for (const m of src.matchAll(INLINE_RE)) {
    if (m.index > last) out.push({ text: src.slice(last, m.index) });
    const tok = m[0];
    if (tok.startsWith("**") || tok.startsWith("__")) out.push({ text: tok.slice(2, -2), bold: true });
    else if (tok.startsWith("`")) out.push({ text: tok.slice(1, -1), code: true });
    else out.push({ text: tok.slice(1, -1), italic: true });
    last = m.index + tok.length;
  }
  if (last < src.length) out.push({ text: src.slice(last) });
  return out;
}

/** Plain text for copying into a decision, task, or the clipboard. */
export function askPlainText(text) {
  return parseAskBlocks(text)
    .map((b) => {
      const flat = (s) => parseAskInline(s).map((r) => r.text).join("");
      if (b.type === "p") return b.lines.map(flat).join("\n");
      if (b.type === "h") return flat(b.text);
      return b.items.map((it, i) => `${b.type === "ol" ? `${i + 1}.` : "-"} ${flat(it)}`).join("\n");
    })
    .join("\n\n");
}

/** First sentence of an answer, trimmed to fit a task title. */
export function askTaskTitle(text, max = 120) {
  const plain = askPlainText(text).replace(/^[-\d.)\s]+/, "").trim();
  const first = (plain.split(/(?<=[.!?])\s|\n/)[0] || plain).trim();
  return first.length > max ? `${first.slice(0, max - 1).trimEnd()}…` : first;
}
