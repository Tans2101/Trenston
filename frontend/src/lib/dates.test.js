import { addDaysISO, formatTimeInTz, thisMonthISO, todayISO } from "./dates";

describe("dates", () => {
  afterEach(() => {
    jest.useRealTimers();
  });

  it("todayISO follows the workspace timezone, not UTC", () => {
    jest.useFakeTimers().setSystemTime(new Date("2026-09-24T23:30:00Z"));
    expect(todayISO("Asia/Manila")).toBe("2026-09-25");
    expect(todayISO("UTC")).toBe("2026-09-24");
    expect(thisMonthISO("Asia/Manila")).toBe("2026-09");
  });

  it("falls back to Asia/Manila for missing or invalid zones", () => {
    jest.useFakeTimers().setSystemTime(new Date("2026-09-24T23:30:00Z"));
    expect(todayISO()).toBe("2026-09-25");
    expect(todayISO("Not/AZone")).toBe("2026-09-25");
  });

  it("addDaysISO does calendar math", () => {
    expect(addDaysISO("2026-03-01", -1)).toBe("2026-02-28");
    expect(addDaysISO("2026-09-25", -30)).toBe("2026-08-26");
  });

  it("formatTimeInTz renders in the given zone", () => {
    expect(formatTimeInTz("2026-09-24T23:30:00Z", "Asia/Manila")).toBe("7:30 AM");
    expect(formatTimeInTz("", "Asia/Manila")).toBe("");
  });
});
