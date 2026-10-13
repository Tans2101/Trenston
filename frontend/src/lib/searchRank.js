/**
 * Ranking for the ⌘K bar. Plain rules, no AI: every word typed has to match
 * something, page names beat keywords, word starts beat the middle of a word,
 * and a one-letter typo on a longer word still finds the page.
 */

const strip = (s) => String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
const words = (s) => strip(s).split(/[^a-z0-9]+/).filter(Boolean);

/** Edit distance, giving up as soon as it is clearly above `max`. */
export function editDistance(a, b, max = 2) {
  if (Math.abs(a.length - b.length) > max) return max + 1;
  let prev = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i += 1) {
    const cur = [i];
    let rowMin = i;
    for (let j = 1; j <= b.length; j += 1) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost);
      if (cur[j] < rowMin) rowMin = cur[j];
    }
    if (rowMin > max) return max + 1;
    prev = cur;
  }
  return prev[b.length];
}

function tokenScore(token, labelWords, label, keyWords, keyText, descText) {
  if (labelWords.some((w) => w.startsWith(token))) return 6;
  if (label.includes(token)) return 4;
  if (keyWords.some((w) => w.startsWith(token))) return 3;
  if (keyText.includes(token)) return 2;
  if (descText.includes(token)) return 1;
  if (token.length >= 4) {
    const max = token.length >= 7 ? 2 : 1;
    const close = (w) => w.length >= 3 && w[0] === token[0] && (editDistance(token, w, max) <= max || editDistance(token, w.slice(0, token.length), max) <= max);
    if (labelWords.some(close)) return 0.25;
    if (keyWords.some(close)) return 0.2;
  }
  return 0;
}

/** Score one action for a query; 0 means it does not match. */
export function scoreAction(action, query) {
  const q = strip(query).trim();
  if (!q) return 1;
  const tokens = q.split(/\s+/);
  const label = strip(action.label);
  const labelWords = words(action.label);
  const keywords = Array.isArray(action.keywords) ? action.keywords : [];
  const keyText = strip(keywords.join(" "));
  const keyWords = words(keywords.join(" "));
  const descText = strip(action.description);
  let total = 0;
  for (const t of tokens) {
    const s = tokenScore(t, labelWords, label, keyWords, keyText, descText);
    if (!s) return 0;
    total += s;
  }
  if (label === q) total += 12;
  else if (label.startsWith(q)) total += 6;
  return total;
}

/** Matching actions, best first. Ties keep their original order. */
export function rankActions(actions, query) {
  if (!strip(query).trim()) return actions;
  const scored = actions
    .map((a, i) => ({ a, i, s: scoreAction(a, query) }))
    .filter((x) => x.s > 0);
  // Typo guesses (scores under 1) only appear when nothing matches properly,
  // so "task" shows Tasks and not also Contact because "talk" is one letter away.
  const sure = scored.filter((x) => x.s >= 1);
  return (sure.length ? sure : scored)
    .sort((x, y) => y.s - x.s || x.i - y.i)
    .map((x) => x.a);
}
