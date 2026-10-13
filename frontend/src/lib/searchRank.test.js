import { editDistance, rankActions, scoreAction } from "@/lib/searchRank";

const A = (id, label, extra = {}) => ({ id, label, ...extra });
const actions = [
  A("settings", "Settings", { description: "Settings", keywords: ["account", "preferences"] }),
  A("tasks", "Tasks", { description: "App" }),
  A("decisions", "Decisions", { description: "App" }),
  A("new-decision", "New decision", { description: "Create", keywords: ["log decision", "add decision"] }),
  A("financials", "Financials", { description: "App", keywords: ["runway", "cash"] }),
  A("billing", "Billing", { description: "Account", keywords: ["plan", "subscription", "payment"] }),
  A("export", "Export data", { description: "Settings", keywords: ["download", "backup"] }),
  A("map", "Company map", { description: "App" }),
];
const ids = (q) => rankActions(actions, q).map((a) => a.id);

describe("rankActions", () => {
  it("returns everything for an empty query", () => {
    expect(rankActions(actions, "  ")).toHaveLength(actions.length);
  });

  it("puts a page whose name starts with the text first", () => {
    expect(ids("dec")[0]).toBe("decisions");
    expect(ids("task")[0]).toBe("tasks");
  });

  it("an exact name beats a longer one", () => {
    expect(ids("decisions")[0]).toBe("decisions");
  });

  it("matches words in any order", () => {
    expect(ids("map company")).toEqual(["map"]);
    expect(ids("data export")).toEqual(["export"]);
  });

  it("every word must match", () => {
    expect(ids("billing zebra")).toEqual([]);
  });

  it("finds pages by their keywords", () => {
    expect(ids("runway")).toEqual(["financials"]);
    expect(ids("subscription")).toEqual(["billing"]);
  });

  it("forgives a typo on longer words", () => {
    expect(ids("finacials")[0]).toBe("financials");
    expect(ids("taks")[0]).toBe("tasks");
    expect(ids("setings")[0]).toBe("settings");
  });

  it("does not guess on short words", () => {
    expect(ids("tsk")).toEqual([]);
  });

  it("ignores case and accents", () => {
    expect(ids("FINANCIALS")[0]).toBe("financials");
    expect(ids("Décisions")[0]).toBe("decisions");
  });

  it("keeps the original order for equal matches", () => {
    const same = [A("a", "Alpha one"), A("b", "Alpha two")];
    expect(rankActions(same, "alpha").map((x) => x.id)).toEqual(["a", "b"]);
  });

  it("scoreAction is zero when nothing matches", () => {
    expect(scoreAction(actions[0], "zzzz")).toBe(0);
  });
});

describe("editDistance", () => {
  it("counts single edits", () => {
    expect(editDistance("tasks", "taks", 2)).toBe(1);
    expect(editDistance("abc", "xyz", 1)).toBeGreaterThan(1);
  });
});

describe("typo matching stays tight", () => {
  it("needs the same first letter, so 'task' does not pull in 'Ask'", () => {
    const list = [A("ask", "Ask Trenston", { description: "App" }), A("tasks", "Tasks", { description: "App" })];
    expect(rankActions(list, "task").map((x) => x.id)).toEqual(["tasks"]);
  });
});

it("typo guesses are dropped when something matches properly", () => {
  const list = [A("contact", "Contact", { keywords: ["talk"] }), A("tasks", "Tasks")];
  expect(rankActions(list, "task").map((x) => x.id)).toEqual(["tasks"]);
  expect(rankActions(list, "taks").map((x) => x.id)).toEqual(["tasks"]);
});
