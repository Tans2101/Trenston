import { isFatalSoftLoad, softRefreshKey } from "./softRefresh";

describe("isFatalSoftLoad", () => {
  test("fatal when error and no cache", () => {
    expect(isFatalSoftLoad({ error: new Error("x"), data: null })).toBe(true);
  });
  test("not fatal when cache exists despite error", () => {
    expect(isFatalSoftLoad({ error: new Error("x"), data: { items: [] } })).toBe(false);
  });
  test("fatal when no data even without error", () => {
    expect(isFatalSoftLoad({ error: null, data: null })).toBe(true);
  });
});

describe("softRefreshKey", () => {
  test("prefers message then code", () => {
    expect(softRefreshKey({ message: "m", code: "c" })).toBe("m");
    expect(softRefreshKey({ code: "c" })).toBe("c");
    expect(softRefreshKey(null)).toBe("soft-refresh");
  });
});
