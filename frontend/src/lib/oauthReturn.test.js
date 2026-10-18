import { isAppPath, rememberOAuthReturn, takeOAuthReturn } from "./oauthReturn";

describe("oauthReturn", () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("returns a signed-out visitor to the in-app page they opened", () => {
    rememberOAuthReturn({ pathname: "/app/tasks", search: "?task=t_1" });
    expect(takeOAuthReturn()).toBe("/app/tasks?task=t_1");
  });

  it("keeps the AI-assistant connection flow working", () => {
    rememberOAuthReturn({ pathname: "/app/oauth/authorize", search: "?client_id=abc&state=xyz" });
    expect(takeOAuthReturn()).toBe("/app/oauth/authorize?client_id=abc&state=xyz");
  });

  it("is single-use", () => {
    rememberOAuthReturn({ pathname: "/app/financials", search: "" });
    expect(takeOAuthReturn()).toBe("/app/financials");
    expect(takeOAuthReturn()).toBeNull();
  });

  it("does not bother remembering the default landing page", () => {
    rememberOAuthReturn({ pathname: "/app", search: "" });
    expect(takeOAuthReturn()).toBeNull();
  });

  it("ignores pages outside the signed-in app", () => {
    rememberOAuthReturn({ pathname: "/pricing", search: "" });
    expect(takeOAuthReturn()).toBeNull();
  });

  it("never returns anything that could leave the app", () => {
    ["//evil.example/app", "https://evil.example/app", "/application", "/app\\evil", "/app/x\nSet-Cookie: a=b", "", null, undefined]
      .forEach((p) => expect(isAppPath(p)).toBe(false));
    ["/app", "/app/", "/app/tasks", "/app?x=1", "/app/tasks?id=1&b=2"]
      .forEach((p) => expect(isAppPath(p)).toBe(true));
    sessionStorage.setItem("trenston_oauth_return", JSON.stringify({ path: "//evil.example", at: Date.now() }));
    expect(takeOAuthReturn()).toBeNull();
  });

  it("forgets a destination left over from half an hour ago", () => {
    sessionStorage.setItem(
      "trenston_oauth_return",
      JSON.stringify({ path: "/app/tasks", at: Date.now() - 31 * 60 * 1000 }),
    );
    expect(takeOAuthReturn()).toBeNull();
  });

  it("does not throw when storage is blocked", () => {
    const blocked = () => { throw new Error("blocked"); };
    jest.spyOn(Storage.prototype, "getItem").mockImplementation(blocked);
    jest.spyOn(Storage.prototype, "setItem").mockImplementation(blocked);
    jest.spyOn(Storage.prototype, "removeItem").mockImplementation(blocked);
    expect(() => rememberOAuthReturn({ pathname: "/app/tasks", search: "" })).not.toThrow();
    expect(takeOAuthReturn()).toBeNull();
  });
});
