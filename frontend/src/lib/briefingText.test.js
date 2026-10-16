import { splitSummary, isOlderThan, isEmptyChange } from "./briefingText";

test("splits after two sentences and keeps the rest", () => {
  const text = "Runway is 4.9 months. Cash hits the reserve in 51 days. MRR is not logged. Add it on Financials.";
  const { preview, rest } = splitSummary(text);
  expect(preview).toBe("Runway is 4.9 months. Cash hits the reserve in 51 days.");
  expect(rest).toBe("MRR is not logged. Add it on Financials.");
  expect(`${preview} ${rest}`).toBe(text);
});

test("short notes are not split, decimals and amounts stay intact", () => {
  expect(splitSummary("Burn is $1.5k. Fine.")).toEqual({ preview: "Burn is $1.5k. Fine.", rest: "" });
  expect(splitSummary("")).toEqual({ preview: "", rest: "" });
  expect(splitSummary("One. Two. $300 left.").rest).toBe("$300 left.");
});

test("stale check", () => {
  const now = Date.parse("2026-10-16T05:00:00Z");
  expect(isOlderThan("2026-10-14T02:37:00Z", 24, now)).toBe(true);
  expect(isOlderThan("2026-10-16T01:00:00Z", 24, now)).toBe(false);
  expect(isOlderThan(null, 24, now)).toBe(false);
  expect(isOlderThan("garbage", 24, now)).toBe(false);
});

test("empty change rows", () => {
  expect(isEmptyChange({ title: "Viewed document library · 0 items" })).toBe(true);
  expect(isEmptyChange({ title: "Viewed document library · 0 item" })).toBe(true);
  expect(isEmptyChange({ title: "Viewed document library · 10 items" })).toBe(false);
  expect(isEmptyChange({ title: "Logged expense · Claude monthly $22 (2026-10)" })).toBe(false);
});

test("long run-on sentences fall back to one sentence", () => {
  const first = "Runway is sitting at 4.9 months with burn around $278, so the cash reserve timeline you accepted yesterday is worth keeping front of mind.";
  const second = "MRR still hasn't been logged, so you're flying without a real revenue picture right now, same with sales targets.";
  const { preview, rest } = splitSummary(`${first} ${second} Log MRR today.`);
  expect(preview).toBe(first);
  expect(rest).toBe(`${second} Log MRR today.`);
});
