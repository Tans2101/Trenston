import {
  clerkSessionComplete,
  shouldHardLogoutStaleTrenstonSession,
} from "@/lib/clerkSession";

describe("shouldHardLogoutStaleTrenstonSession", () => {
  const base = {
    clerkReady: true,
    user: { id: "u1" },
    clerkComplete: false,
    sessionStatus: null,
    isSignedIn: false,
    userId: null,
    sessionId: null,
    session: null,
  };

  it("logs out only when Clerk is explicitly signed out", () => {
    expect(shouldHardLogoutStaleTrenstonSession(base)).toBe(true);
  });

  it("does not logout while email verification is pending", () => {
    expect(shouldHardLogoutStaleTrenstonSession({
      ...base,
      sessionStatus: "pending",
      isSignedIn: true,
      userId: "clerk_1",
    })).toBe(false);
  });

  it("does not logout during Clerk hydration gaps", () => {
    expect(shouldHardLogoutStaleTrenstonSession({
      ...base,
      isSignedIn: undefined,
      userId: "clerk_1",
    })).toBe(false);
  });

  it("does not logout when Clerk session is complete", () => {
    expect(shouldHardLogoutStaleTrenstonSession({
      ...base,
      clerkComplete: true,
      isSignedIn: true,
      userId: "clerk_1",
    })).toBe(false);
  });
});

describe("clerkSessionComplete", () => {
  it("treats pending as incomplete", () => {
    expect(clerkSessionComplete({
      isSignedIn: true,
      userId: "c1",
      sessionId: "s1",
      session: {},
      sessionStatus: "pending",
    })).toBe(false);
  });
});
