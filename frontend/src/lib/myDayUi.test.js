import {
  hasMyDaySoftRefreshError,
  isFatalMyDayFeed,
  isMyDayInitialLoading,
  isSoftMyDayFeedError,
} from "./myDayUi";

describe("isSoftMyDayFeedError", () => {
  it("is true only when error and cached data both exist", () => {
    expect(isSoftMyDayFeedError(new Error("x"), { notes: [] })).toBe(true);
    expect(isSoftMyDayFeedError(new Error("x"), null)).toBe(false);
    expect(isSoftMyDayFeedError(null, { notes: [] })).toBe(false);
  });
});

describe("isFatalMyDayFeed", () => {
  it("is fatal when error and no data", () => {
    expect(isFatalMyDayFeed(new Error("x"), null)).toBe(true);
  });
  it("is not fatal when cached data remains", () => {
    expect(isFatalMyDayFeed(new Error("x"), { items: [] })).toBe(false);
  });
});

describe("isMyDayInitialLoading", () => {
  it("waits only when every feed is loading without cache", () => {
    expect(isMyDayInitialLoading([
      { loading: true, data: null },
      { loading: true, data: null },
    ])).toBe(true);
    expect(isMyDayInitialLoading([
      { loading: true, data: null },
      { loading: false, data: { items: [] } },
    ])).toBe(false);
  });
});

describe("hasMyDaySoftRefreshError", () => {
  it("detects any soft-refresh feed", () => {
    expect(hasMyDaySoftRefreshError([
      { error: null, data: { a: 1 } },
      { error: new Error("fail"), data: { b: 2 } },
    ])).toBe(true);
    expect(hasMyDaySoftRefreshError([
      { error: new Error("fail"), data: null },
    ])).toBe(false);
  });
});
