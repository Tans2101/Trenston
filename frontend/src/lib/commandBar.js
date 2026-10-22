/**
 * Quick-add command parsing for the ⌘K bar. Plain rules, no AI, so the same
 * words always give the same result. Nothing is saved from here: the bar shows
 * what was understood and waits for Enter.
 *
 * Examples:
 *   task call the supplier friday for Ann !high #sales
 *   remind me to send the invoice on oct 20
 *   decision hire a second developer by next week
 *   note ask Sam about the lease
 */

const WEEKDAYS = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"];
const WEEKDAY_SHORT = {
  sun: 0, mon: 1, tue: 2, tues: 2, wed: 3, thu: 4, thur: 4, thurs: 4, fri: 5, sat: 6,
};
const MONTHS = [
  "january", "february", "march", "april", "may", "june", "july",
  "august", "september", "october", "november", "december",
];
const MONTH_SHORT = {
  jan: 0, feb: 1, mar: 2, apr: 3, jun: 5, jul: 6, aug: 7, sep: 8, sept: 8, oct: 9, nov: 10, dec: 11,
};

const COMMANDS = [
  { kind: "task", re: /^(?:add\s+(?:a\s+)?task|new\s+task|task|to-?do|todo|remind\s+me\s+to|reminder)\b[:\s]*/i },
  { kind: "decision", re: /^(?:new\s+decision|decision)\b[:\s]*/i },
  // "decide on pricing" reads as the decision itself, so the whole sentence is kept as the title.
  { kind: "decision", keep: true, re: /^decide\b[:\s]*/i },
  { kind: "note", re: /^(?:add\s+(?:a\s+)?note|new\s+note|note|jot)\b[:\s]*/i },
];

export const KIND_LABEL = { task: "New task", decision: "New decision", note: "New private note" };

const pad = (n) => String(n).padStart(2, "0");

function isoOf(y, m, d) {
  return `${y}-${pad(m + 1)}-${pad(d)}`;
}

function dateFrom(y, m, d) {
  return new Date(Date.UTC(y, m, d));
}

function toIso(date) {
  return isoOf(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate());
}

function addDays(date, n) {
  return dateFrom(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate() + n);
}

/** Human date for the preview, e.g. "Fri 23 Oct". The year is added when it is not this year, so a date that rolled into next year is visible. */
export function prettyDate(iso, now = new Date()) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(iso || "")) return "";
  const [y, m, d] = iso.split("-").map(Number);
  const dt = dateFrom(y, m - 1, d);
  const wd = WEEKDAYS[dt.getUTCDay()].slice(0, 3);
  const mon = MONTHS[m - 1].slice(0, 3);
  const year = y === now.getFullYear() ? "" : ` ${y}`;
  return `${wd[0].toUpperCase()}${wd.slice(1)} ${d} ${mon[0].toUpperCase()}${mon.slice(1)}${year}`;
}

function nextWeekday(today, wd, { allowToday = false } = {}) {
  let diff = (wd - today.getUTCDay() + 7) % 7;
  if (diff === 0 && !allowToday) diff = 7;
  return addDays(today, diff);
}

function daysInMonth(y, m) {
  return new Date(Date.UTC(y, m + 1, 0)).getUTCDate();
}

/** Month + day -> the next such date on or after today (so "Jan 5" in December means next year). */
function monthDay(today, month, day) {
  if (day < 1 || day > 31) return null;
  let y = today.getUTCFullYear();
  if (day > daysInMonth(y, month)) return null;
  let candidate = dateFrom(y, month, day);
  if (candidate < today) {
    y += 1;
    if (day > daysInMonth(y, month)) return null;
    candidate = dateFrom(y, month, day);
  }
  return candidate;
}

const LEAD = "(?:(?:by|on|due|before|until|for)\\s+)?";
const LEAD_REQUIRED = "(?:by|on|due|before|until|for)\\s+";
const hasLead = (m) => /^\s*(?:by|on|due|before|until|for)\s/i.test(m[0]);
/** "may" is also a verb ("may 5 invoices"), so on its own it is not a month. Skipped matches return undefined. */
const bareMay = (m, word) => /^may$/i.test(word) && !hasLead(m);

/** Day and month typed as numbers. Day first (12/10 is 12 October) unless the first number can only be a month. */
function numericDate(today, a, b, yearText) {
  let d = a;
  let mo = b;
  if (a <= 12 && b > 12) { mo = a; d = b; }
  if (mo < 1 || mo > 12 || d < 1) return null;
  if (yearText) {
    const y = yearText.length === 2 ? 2000 + Number(yearText) : Number(yearText);
    return d <= daysInMonth(y, mo - 1) ? dateFrom(y, mo - 1, d) : null;
  }
  return monthDay(today, mo - 1, d);
}

/** The next time this day-of-month comes round (this month if it has not passed). */
function nextDayOfMonth(today, day) {
  if (day < 1 || day > 31) return null;
  for (let add = 0; add < 3; add += 1) {
    const y = today.getUTCFullYear() + Math.floor((today.getUTCMonth() + add) / 12);
    const mo = (today.getUTCMonth() + add) % 12;
    if (day > daysInMonth(y, mo)) continue;
    const cand = dateFrom(y, mo, day);
    if (cand >= today) return cand;
  }
  return null;
}
const wdAlt = WEEKDAYS.join("|");
const wdShortAlt = Object.keys(WEEKDAY_SHORT).sort((a, b) => b.length - a.length).join("|");
const monAlt = MONTHS.join("|");
const monShortAlt = Object.keys(MONTH_SHORT).sort((a, b) => b.length - a.length).join("|");

/** [regex, resolver(match, today) -> Date|null]; the first group set is always the whole phrase. */
function datePatterns() {
  return [
    [new RegExp(`\\b${LEAD}(\\d{4})-(\\d{2})-(\\d{2})\\b`, "i"), (m) => {
      const y = +m[1]; const mo = +m[2] - 1; const d = +m[3];
      return mo >= 0 && mo < 12 && d >= 1 && d <= daysInMonth(y, mo) ? dateFrom(y, mo, d) : null;
    }],
    [new RegExp(`\\b${LEAD}(?:the\\s+)?(\\d{1,2})(?:st|nd|rd|th)?\\s+(?:of\\s+)?(${monAlt}|${monShortAlt})\\b\\.?(?!\\s*\\d)`, "i"),
      (m, today) => (bareMay(m, m[2]) ? undefined : monthDay(today, monthIndex(m[2]), +m[1]))],
    [new RegExp(`\\b${LEAD}(${monAlt}|${monShortAlt})\\.?\\s+(\\d{1,2})(?:st|nd|rd|th)?\\b(?!\\s*[:\\d])`, "i"),
      (m, today) => (bareMay(m, m[1]) ? undefined : monthDay(today, monthIndex(m[1]), +m[2]))],
    // "on the 5th", "by 1st": the next time that day of the month comes round.
    [new RegExp(`\\b(?:${LEAD_REQUIRED}(?:the\\s+)?|the\\s+)(\\d{1,2})(?:st|nd|rd|th)\\b`, "i"),
      (m, today) => nextDayOfMonth(today, +m[1])],
    // 12/10 or 12/10/2026, day first. Without a lead-in word a year is needed, so fractions like 3/4 stay put.
    [new RegExp(`\\b${LEAD_REQUIRED}(\\d{1,2})/(\\d{1,2})(?:/(\\d{4}|\\d{2}))?\\b`, "i"),
      (m, today) => numericDate(today, +m[1], +m[2], m[3])],
    [new RegExp(`\\b(\\d{1,2})[/.](\\d{1,2})[/.](\\d{4})\\b`, "i"),
      (m, today) => numericDate(today, +m[1], +m[2], m[3])],
    [new RegExp(`\\b${LEAD}next\\s+month\\b`, "i"),
      (m, today) => dateFrom(today.getUTCFullYear(), today.getUTCMonth() + 1, 1)],
    [new RegExp(`\\b${LEAD}next\\s+quarter\\b`, "i"),
      (m, today) => dateFrom(today.getUTCFullYear(), (Math.floor(today.getUTCMonth() / 3) + 1) * 3, 1)],
    [new RegExp(`\\b${LEAD}in\\s+(\\d{1,2})\\s+months?\\b`, "i"), (m, today) => {
      const total = today.getUTCMonth() + +m[1];
      const y = today.getUTCFullYear() + Math.floor(total / 12);
      const mo = total % 12;
      return dateFrom(y, mo, Math.min(today.getUTCDate(), daysInMonth(y, mo)));
    }],
    [new RegExp(`\\b${LEAD}in\\s+(\\d{1,3})\\s+(day|days|week|weeks)\\b`, "i"), (m, today) => {
      const n = +m[1];
      return addDays(today, /^week/i.test(m[2]) ? n * 7 : n);
    }],
    [new RegExp(`\\b${LEAD}next\\s+week\\b`, "i"), (m, today) => nextWeekday(today, 1)],
    [new RegExp(`\\b${LEAD}(?:end\\s+of\\s+(?:the\\s+)?week|eow)\\b`, "i"), (m, today) => {
      const dow = today.getUTCDay();
      if (dow === 5) return today;
      return nextWeekday(today, 5);
    }],
    [new RegExp(`\\b${LEAD}(?:end\\s+of\\s+(?:the\\s+)?month|eom)\\b`, "i"),
      (m, today) => dateFrom(today.getUTCFullYear(), today.getUTCMonth(), daysInMonth(today.getUTCFullYear(), today.getUTCMonth()))],
    [new RegExp(`\\b${LEAD}next\\s+(${wdAlt}|${wdShortAlt})\\b`, "i"), (m, today) => {
      const wd = weekdayIndex(m[1]);
      // The named day in the week that starts after this one: next Monday + offset.
      const nextMonday = nextWeekday(today, 1);
      return addDays(nextMonday, (wd + 6) % 7);
    }],
    [new RegExp(`\\b${LEAD}this\\s+(${wdAlt}|${wdShortAlt})\\b`, "i"),
      (m, today) => nextWeekday(today, weekdayIndex(m[1]), { allowToday: true })],
    [new RegExp(`\\b(?:(?:by|on|due|before|until)\\s+)?(${wdAlt})\\b`, "i"),
      (m, today) => nextWeekday(today, weekdayIndex(m[1]))],
    // Short weekday names are common words ("sat", "mon"), so they need a lead-in.
    [new RegExp(`\\b(?:by|on|due|before|until)\\s+(${wdShortAlt})\\b`, "i"),
      (m, today) => nextWeekday(today, weekdayIndex(m[1]))],
    // A short weekday as the very last word ("send the deck mon"). Sat and sun are left out: too often a name or a verb.
    [/(?<=\S\s+)\b(mon|tue|tues|wed|thu|thur|thurs|fri)\b\.?(?=\s*[.!]?\s*$)/i,
      (m, today) => nextWeekday(today, weekdayIndex(m[1]))],
    [new RegExp(`\\b${LEAD}day\\s+after\\s+tomorrow\\b`, "i"), (m, today) => addDays(today, 2)],
    [new RegExp(`\\b${LEAD}tomorrow\\b`, "i"), (m, today) => addDays(today, 1)],
    [new RegExp(`\\b${LEAD}(?:today|tonight)\\b`, "i"), (m, today) => today],
  ];
}

function weekdayIndex(word) {
  const w = word.toLowerCase();
  const full = WEEKDAYS.indexOf(w);
  return full >= 0 ? full : WEEKDAY_SHORT[w];
}

function monthIndex(word) {
  const w = word.toLowerCase();
  const full = MONTHS.indexOf(w);
  return full >= 0 ? full : MONTH_SHORT[w.replace(/\.$/, "")];
}

/** Find every date phrase. Returns [{start, end, date}], earlier matches winning overlaps. */
function findDates(text, today) {
  const found = [];
  for (const [re, resolve] of datePatterns()) {
    const g = new RegExp(re.source, "gi");
    let m;
    // eslint-disable-next-line no-cond-assign
    while ((m = g.exec(text)) !== null) {
      const start = m.index;
      const end = start + m[0].length;
      if (found.some((f) => start < f.end && end > f.start)) continue;
      const date = resolve(m, today);
      if (date === undefined) continue;
      found.push({ start, end, date, text: m[0] });
    }
  }
  return found.sort((a, b) => a.start - b.start);
}

function removeRanges(text, ranges) {
  let out = text;
  [...ranges].sort((a, b) => b.start - a.start).forEach((r) => {
    out = `${out.slice(0, r.start)} ${out.slice(r.end)}`;
  });
  return out;
}

function priorityFrom(text) {
  const rules = [
    [/(?:^|\s)!(?:high|urgent|h)\b/i, "High"],
    [/(?:^|\s)!(?:medium|med|m)\b/i, "Medium"],
    [/(?:^|\s)!(?:low|l)\b/i, "Low"],
    [/\b(?:high|top)[\s-]priority\b/i, "High"],
    [/\bmedium[\s-]priority\b/i, "Medium"],
    [/\blow[\s-]priority\b/i, "Low"],
    // Bare "urgent" / "asap" only count at the very start or end, not inside a title.
    [/\s(?:urgent|asap)\s*[.!]*$/i, "High"],
    [/^(?:urgent|asap)(?:\s*[:,-]\s*|\s+)/i, "High"],
  ];
  for (const [re, level] of rules) {
    const m = re.exec(text);
    if (m) return { level, start: m.index, end: m.index + m[0].length };
  }
  return null;
}

function nameKeys(member) {
  const full = (member.name || "").trim().toLowerCase();
  const first = full.split(/\s+/)[0] || "";
  const local = (member.email || "").split("@")[0].toLowerCase();
  return { full, first, local };
}

function memberLabel(m) {
  return (m.name || m.email || "Teammate").trim();
}

/**
 * Who does this word (or two words) mean? Returns { status: "one"|"many"|"none", matches }.
 * "Ann" matches a first name, a full name, or an email prefix; if two people share it, it is "many".
 */
export function matchMember(words, members, myUserId) {
  const q = words.join(" ").trim().toLowerCase();
  if (!q) return { status: "none", matches: [] };
  if (["me", "myself"].includes(q)) {
    const me = members.find((m) => m.user_id === myUserId || m.is_self);
    return me ? { status: "one", matches: [me], self: true } : { status: "none", matches: [] };
  }
  const exact = members.filter((m) => nameKeys(m).full === q);
  if (exact.length === 1) return { status: "one", matches: exact };
  const loose = members.filter((m) => {
    const k = nameKeys(m);
    return k.full === q || k.first === q || k.local === q;
  });
  if (loose.length === 1) return { status: "one", matches: loose };
  if (loose.length > 1) return { status: "many", matches: loose };
  return { status: "none", matches: [] };
}

const ASSIGN_RE = /\b((?:assign(?:ed)?\s+to|for)\s+@?)([A-Za-z][A-Za-z.'-]*)(?:\s+([A-Za-z][A-Za-z.'-]*))?/gi;
const AT_RE = /(^|\s)@([A-Za-z][\w.'-]*)/g;

function findAssignee(text, members, myUserId) {
  const people = (members || []).filter((m) => m.user_id && m.status !== "invited");

  // "@name": an explicit mention, so an unknown name is a problem rather than part of the title.
  const at = new RegExp(AT_RE.source, "g").exec(text);
  if (at) {
    const start = at.index + at[1].length;
    const res = matchMember([at[2]], people, myUserId);
    return { ...res, explicit: true, word: at[2], start, end: at.index + at[0].length };
  }

  const g = new RegExp(ASSIGN_RE.source, "gi");
  let m;
  // eslint-disable-next-line no-cond-assign
  while ((m = g.exec(text)) !== null) {
    const explicit = /assign/i.test(m[1]);
    const lead = m[1].length;
    // Try the two-word name first ("Ann Lee"), then just the first word ("Ann").
    if (m[3]) {
      const two = matchMember([m[2], m[3]], people, myUserId);
      if (two.status === "one") {
        return { ...two, explicit, word: `${m[2]} ${m[3]}`, start: m.index, end: m.index + m[0].length };
      }
    }
    const one = matchMember([m[2]], people, myUserId);
    const end = m.index + lead + m[2].length;
    if (one.status !== "none") {
      return { ...one, explicit, word: m[2], start: m.index, end };
    }
    if (explicit) {
      return { status: "none", matches: [], explicit, word: m[2], start: m.index, end };
    }
  }
  return null;
}

function tidyTitle(text) {
  let t = text.replace(/\s+/g, " ").trim();
  // Leave-overs from removed phrases: dangling connectors at the ends.
  t = t.replace(/^(?:to|that|about|:|-)\s+/i, "");
  for (let i = 0; i < 3; i += 1) {
    t = t.replace(/\s+(?:by|on|due|before|until|for|to|at|and|,)\s*$/i, "").replace(/[\s,;:-]+$/, "");
  }
  t = t.replace(/^[\s,;:-]+/, "");
  return t.charAt(0).toUpperCase() + t.slice(1);
}

/**
 * Turn what was typed into a draft. Returns null when it is not a command
 * (so the bar keeps behaving like search).
 *
 * @param {string} input
 * @param {{ now?: Date, members?: Array, myUserId?: string, assigneeId?: string }} [opts]
 *   assigneeId: the person picked by the user when the name was ambiguous.
 */
export function parseCommand(input, opts = {}) {
  const raw = String(input || "").replace(/^\s+/, "");
  const command = COMMANDS.find((c) => c.re.test(raw));
  if (!command) return null;
  const stripped = raw.replace(command.re, "");
  // A bare "task", "decision" or "note" is someone looking for that page, not starting an entry.
  // It becomes a command once there is a space or colon after it.
  if (!stripped.trim() && !/[\s:]$/.test(raw)) return null;
  const rest = command.keep ? raw : stripped;
  const now = opts.now || new Date();
  const today = dateFrom(now.getFullYear(), now.getMonth(), now.getDate());
  const members = opts.members || [];
  const issues = [];
  const out = {
    kind: command.kind, title: "", due: "", priority: "", tag: "", assignee: null,
    ambiguous: null, issues,
  };

  if (command.kind === "note") {
    out.title = rest.trim().slice(0, 800);
    if (!out.title) issues.push("Write the note after the word note.");
    return finish(out);
  }

  let text = ` ${rest} `;

  if (command.kind === "task") {
    const tag = /(?:^|\s)#([A-Za-z][\w-]*)/.exec(text);
    if (tag) {
      out.tag = tag[1];
      text = removeRanges(text, [{ start: tag.index, end: tag.index + tag[0].length }]);
    }
  }

  const trimmed = text.trim();
  const pr = priorityFrom(trimmed);
  if (pr) {
    out.priority = pr.level;
    text = ` ${removeRanges(trimmed, [pr])} `;
  }

  if (command.kind === "task") {
    const who = findAssignee(text, members, opts.myUserId);
    if (who) {
      if (who.status === "one") {
        const person = who.matches[0];
        out.assignee = { user_id: person.user_id, name: memberLabel(person), self: Boolean(who.self) };
        text = removeRanges(text, [who]);
      } else if (who.status === "many") {
        const pick = opts.assigneeId ? who.matches.find((p) => p.user_id === opts.assigneeId) : null;
        if (pick) {
          out.assignee = { user_id: pick.user_id, name: memberLabel(pick), self: false };
          text = removeRanges(text, [who]);
        } else {
          out.ambiguous = {
            field: "assignee",
            word: who.word,
            options: who.matches.map((p) => ({ user_id: p.user_id, name: memberLabel(p) })),
          };
          text = removeRanges(text, [who]);
        }
      } else if (who.explicit) {
        issues.push(members.length
          ? `I don't know anyone called "${who.word}" on your team.`
          : "I couldn't load your team yet, try again in a moment.");
        text = removeRanges(text, [who]);
      }
      // A plain "for mum" that matches nobody stays in the title.
    }
  }

  const dates = findDates(text, today);
  if (dates.length > 1) {
    issues.push(`I found more than one date ("${dates[0].text.trim()}" and "${dates[1].text.trim()}"). Keep just one.`);
  }
  if (dates.length >= 1) {
    const valid = dates.filter((d) => d.date);
    const invalid = dates.filter((d) => !d.date);
    if (invalid.length) issues.push(`"${invalid[0].text.trim()}" isn't a real date.`);
    if (valid.length) out.due = toIso(valid[0].date);
    text = removeRanges(text, dates);
  }

  out.title = tidyTitle(text);
  if (!out.title) {
    issues.push(command.kind === "task" ? "Say what the task is." : "Say what the decision is about.");
  }
  if (command.kind === "decision" && out.assignee) out.assignee = null;
  return finish(out);
}

function finish(out) {
  const ready = out.issues.length === 0 && !out.ambiguous && Boolean(out.title);
  return { ...out, ready };
}

/** The request each kind sends to the existing create endpoints. */
export function requestFor(parsed, { myUserId } = {}) {
  if (parsed.kind === "task") {
    const body = {
      title: parsed.title,
      priority: parsed.priority || "Medium",
      tag: parsed.tag || "General",
      due: parsed.due || "",
    };
    if (parsed.assignee && parsed.assignee.user_id !== myUserId) body.assignee_user_id = parsed.assignee.user_id;
    return { path: "/tasks", body, done: "Task created", view: "/app/tasks" };
  }
  if (parsed.kind === "decision") {
    return {
      path: "/decisions",
      body: {
        title: parsed.title,
        due: parsed.due || "",
        impact: parsed.priority || "Medium",
      },
      done: "Decision logged",
      view: "/app/decisions",
    };
  }
  // Notes surface on Home / My Day at /app (there is no /app/myday route).
  return { path: "/notes", body: { text: parsed.title }, done: "Note saved", view: "/app" };
}
