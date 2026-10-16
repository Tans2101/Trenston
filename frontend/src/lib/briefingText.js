/** Text helpers for Home: keep the first read short without hiding anything. */

// Sentence ends: . ! or ? followed by whitespace and a new sentence start.
// Decimals ("$1.5k") and initials without a following space are not split.
const SENTENCE_BREAK = /(?<=[.!?])\s+(?=[A-Z0-9$"'(])/;

/**
 * Split an AI note into a short preview and the rest.
 * The rest is shown behind "Show more", never dropped.
 */
export function splitSummary(text, sentences = 2, maxChars = 220) {
  const t = String(text || "").trim();
  if (!t) return { preview: "", rest: "" };
  const parts = t.split(SENTENCE_BREAK);
  let n = Math.min(sentences, parts.length);
  // Long run-on sentences: show fewer so the first read stays short.
  while (n > 1 && parts.slice(0, n).join(" ").length > maxChars) n -= 1;
  if (n >= parts.length) return { preview: t, rest: "" };
  return {
    preview: parts.slice(0, n).join(" "),
    rest: parts.slice(n).join(" "),
  };
}

/** True when an ISO timestamp is older than `hours` (default one day). */
export function isOlderThan(iso, hours = 24, now = Date.now()) {
  if (!iso) return false;
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return false;
  return now - t > hours * 3600 * 1000;
}

/** "Viewed document library · 0 items" and similar rows say nothing changed. */
export function isEmptyChange(item) {
  return /(^|\s|·)0 items?\s*$/i.test(String(item?.title || "").trim());
}
