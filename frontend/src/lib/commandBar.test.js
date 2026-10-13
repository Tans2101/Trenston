import { matchMember, parseCommand, prettyDate, requestFor } from "@/lib/commandBar";

// Tuesday 13 Oct 2026
const now = new Date(2026, 9, 13, 9, 0, 0);
const members = [
  { user_id: "u_me", name: "Tansher Dhawan", email: "t@x.com", is_self: true },
  { user_id: "u_ann", name: "Ann Lee", email: "ann@x.com" },
  { user_id: "u_bob1", name: "Bob Stone", email: "bob@x.com" },
  { user_id: "u_bob2", name: "Bob Reyes", email: "bobr@x.com" },
  { user_id: "u_inv", name: "Invited Ivy", email: "ivy@x.com", status: "invited" },
];
const p = (text, extra = {}) => parseCommand(text, { now, members, myUserId: "u_me", ...extra });

describe("is it a command?", () => {
  it("ignores normal searches", () => {
    expect(p("billing")).toBeNull();
    expect(p("tasks board")).toBeNull();
    expect(p("notes")).toBeNull();
    expect(p("")).toBeNull();
    expect(p("decisions")).toBeNull();
  });

  it("understands the verbs", () => {
    expect(p("task call supplier").kind).toBe("task");
    expect(p("todo call supplier").kind).toBe("task");
    expect(p("remind me to call supplier").kind).toBe("task");
    expect(p("add task call supplier").kind).toBe("task");
    expect(p("decision hire a developer").kind).toBe("decision");
    expect(p("decide on pricing").kind).toBe("decision");
    expect(p("note ask Sam about the lease").kind).toBe("note");
  });
});

describe("dates (today is Tue 13 Oct 2026)", () => {
  const due = (text) => p(`task x ${text}`).due;
  it("handles relative words", () => {
    expect(due("today")).toBe("2026-10-13");
    expect(due("tomorrow")).toBe("2026-10-14");
    expect(due("in 3 days")).toBe("2026-10-16");
    expect(due("in 2 weeks")).toBe("2026-10-27");
    expect(due("next week")).toBe("2026-10-19");
    expect(due("end of week")).toBe("2026-10-16");
    expect(due("eom")).toBe("2026-10-31");
  });

  it("handles weekdays as the next time that day comes", () => {
    expect(due("friday")).toBe("2026-10-16");
    expect(due("by friday")).toBe("2026-10-16");
    expect(due("tuesday")).toBe("2026-10-20"); // not today
    expect(due("this tuesday")).toBe("2026-10-13");
    expect(due("next friday")).toBe("2026-10-23");
    expect(due("next monday")).toBe("2026-10-19");
  });

  it("handles calendar dates and rolls past ones to next year", () => {
    expect(due("oct 20")).toBe("2026-10-20");
    expect(due("20 october")).toBe("2026-10-20");
    expect(due("on the 5th of nov")).toBe("2026-11-05");
    expect(due("jan 5")).toBe("2027-01-05");
    expect(due("2026-12-01")).toBe("2026-12-01");
    expect(due("oct 13")).toBe("2026-10-13");
  });

  it("does not mistake ordinary words for dates", () => {
    expect(p("task sat with the auditor").due).toBe("");
    expect(p("task call may about the lease").due).toBe("");
    expect(p("task review march 2027 report").due).toBe("");
    expect(p("task mon").due).toBe("");
  });

  it("refuses two dates and impossible ones instead of guessing", () => {
    const two = p("task call supplier friday or monday");
    expect(two.ready).toBe(false);
    expect(two.issues[0]).toMatch(/more than one date/);
    const bad = p("task pay rent feb 30");
    expect(bad.ready).toBe(false);
    expect(bad.issues.join(" ")).toMatch(/isn't a real date/);
  });
});

describe("tasks", () => {
  it("pulls apart title, date, person, priority and tag", () => {
    const r = p("task call the supplier by friday for Ann !high #sales");
    expect(r).toMatchObject({
      kind: "task", title: "Call the supplier", due: "2026-10-16", priority: "High", tag: "sales", ready: true,
    });
    expect(r.assignee).toMatchObject({ user_id: "u_ann", name: "Ann Lee" });
  });

  it("keeps people-like words in the title when they match nobody", () => {
    const r = p("task buy a gift for mum tomorrow");
    expect(r.title).toBe("Buy a gift for mum");
    expect(r.assignee).toBeNull();
    expect(r.ready).toBe(true);
  });

  it("does not assign on 'talk to <name>'", () => {
    const r = p("task talk to Ann about the budget");
    expect(r.assignee).toBeNull();
    expect(r.title).toBe("Talk to Ann about the budget");
  });

  it("asks which Bob when the name is ambiguous, and accepts the answer", () => {
    const r = p("task send contract for Bob");
    expect(r.ready).toBe(false);
    expect(r.ambiguous.options.map((o) => o.user_id)).toEqual(["u_bob1", "u_bob2"]);
    const picked = p("task send contract for Bob", { assigneeId: "u_bob2" });
    expect(picked.ready).toBe(true);
    expect(picked.assignee.user_id).toBe("u_bob2");
    expect(picked.title).toBe("Send contract");
  });

  it("a full name settles the ambiguity", () => {
    const r = p("task send contract for Bob Stone");
    expect(r.ready).toBe(true);
    expect(r.assignee.user_id).toBe("u_bob1");
  });

  it("blocks an explicit mention of someone who is not on the team", () => {
    const r = p("task send contract @zoe");
    expect(r.ready).toBe(false);
    expect(r.issues[0]).toMatch(/zoe/);
    expect(p("task send contract assign to Zoe").ready).toBe(false);
  });

  it("does not offer people who were only invited", () => {
    expect(p("task call for Ivy").assignee).toBeNull();
  });

  it("'me' means you", () => {
    const r = p("task file taxes for me");
    expect(r.assignee).toMatchObject({ user_id: "u_me", self: true });
    expect(requestFor(r, { myUserId: "u_me" }).body.assignee_user_id).toBeUndefined();
  });

  it("only treats urgent as priority at the edges of the sentence", () => {
    expect(p("task call urgent care clinic").priority).toBe("");
    expect(p("task call the bank asap").priority).toBe("High");
    expect(p("task call the bank low priority").priority).toBe("Low");
    expect(p("task call the bank !low").priority).toBe("Low");
  });

  it("will not save an empty task", () => {
    const r = p("task tomorrow");
    expect(r.ready).toBe(false);
    expect(r.issues[0]).toMatch(/what the task is/);
    expect(p("task").ready).toBe(false);
  });

  it("builds the request for the existing endpoint", () => {
    const req = requestFor(p("task call the supplier by friday for Ann !high #sales"), { myUserId: "u_me" });
    expect(req).toMatchObject({ path: "/tasks", done: "Task created" });
    expect(req.body).toEqual({
      title: "Call the supplier", priority: "High", tag: "sales", due: "2026-10-16", assignee_user_id: "u_ann",
    });
    expect(requestFor(p("task plain"), { myUserId: "u_me" }).body).toEqual({
      title: "Plain", priority: "Medium", tag: "General", due: "",
    });
  });
});

describe("decisions and notes", () => {
  it("decisions take a date and impact but never an assignee", () => {
    const r = p("decision hire a second developer by next week !high");
    expect(r).toMatchObject({ kind: "decision", title: "Hire a second developer", due: "2026-10-19", priority: "High", ready: true });
    expect(requestFor(r)).toMatchObject({
      path: "/decisions", body: { title: "Hire a second developer", due: "2026-10-19", impact: "High" },
    });
    expect(p("decision hire for Ann").assignee).toBeNull();
  });

  it("notes keep the text exactly as written", () => {
    const r = p("note call Ann friday !high #x");
    expect(r.title).toBe("call Ann friday !high #x");
    expect(r.due).toBe("");
    expect(requestFor(r)).toMatchObject({ path: "/notes", body: { text: "call Ann friday !high #x" } });
    expect(p("note").ready).toBe(false);
  });
});

describe("helpers", () => {
  it("prettyDate", () => {
    expect(prettyDate("2026-10-23")).toBe("Fri 23 Oct");
    expect(prettyDate("")).toBe("");
  });

  it("matchMember", () => {
    expect(matchMember(["ann"], members, "u_me").status).toBe("one");
    expect(matchMember(["bob"], members, "u_me").status).toBe("many");
    expect(matchMember(["nobody"], members, "u_me").status).toBe("none");
  });
});
