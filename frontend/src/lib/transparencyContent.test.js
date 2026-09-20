/**
 * @jest-environment node
 */
import { CHANGELOG_ENTRIES, CHANGELOG_INTRO, getChangelogEntries } from "./changelog";
import data from "./changelog.json";
import { STATUS_DISCLAIMER, STATUS_TRACKING_STARTED, STATUS_INCIDENTS } from "./statusConfig";
import { PUBLIC_INTEGRATIONS_COMING_SOON } from "./marketingCopy";

describe("transparency content", () => {
  test("changelog comes only from hand-edited changelog.json", () => {
    expect(CHANGELOG_INTRO.toLowerCase()).toContain("not a roadmap");
    expect(CHANGELOG_INTRO.toLowerCase()).toMatch(/hand|plain language/);
    const entries = getChangelogEntries();
    expect(entries.length).toBe(data.entries.length);
    expect(entries.length).toBeGreaterThanOrEqual(4);
    for (const e of entries) {
      expect(e.date).toMatch(/^\d{4}-\d{2}-\d{2}$/);
      expect(e.title.length).toBeGreaterThan(8);
      expect(e.description.length).toBeGreaterThan(20);
      expect(e).not.toHaveProperty("body");
      expect(e).not.toHaveProperty("commit");
      expect(e).not.toHaveProperty("sha");
    }
    // Newest date first
    for (let i = 1; i < entries.length; i += 1) {
      expect(entries[i - 1].date >= entries[i].date).toBe(true);
    }
    expect(CHANGELOG_ENTRIES.length).toBe(entries.length);
  });

  test("status page does not invent historical uptime", () => {
    expect(STATUS_TRACKING_STARTED).toBe("2026-09-19");
    expect(STATUS_DISCLAIMER.toLowerCase()).toContain("do not publish historical uptime");
    expect(Array.isArray(STATUS_INCIDENTS)).toBe(true);
  });

  test("GitHub stays labeled coming soon on public marketing", () => {
    expect(PUBLIC_INTEGRATIONS_COMING_SOON.some((i) => i.id === "github")).toBe(true);
    expect(PUBLIC_INTEGRATIONS_COMING_SOON.every((i) => /not available|not shipped|planned/i.test(i.description))).toBe(true);
  });
});
