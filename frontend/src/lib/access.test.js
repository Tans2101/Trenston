import { packLockedSections, VIEW_SECTIONS_BY_PACK } from "@/lib/access";

describe("packLockedSections", () => {
  it("marks Financials as pack-locked for Executive even when from_pack omits it", () => {
    expect(VIEW_SECTIONS_BY_PACK.exec).toContain("financials");
    const locked = packLockedSections({
      pack: "exec",
      from_pack: ["telemetry"], // write-only sections_for_perms — no financials
    });
    expect(locked.has("financials")).toBe(true);
    expect(locked.has("telemetry")).toBe(true);
  });

  it("does not invent Financials lock for Member", () => {
    const locked = packLockedSections({ pack: "member", from_pack: [] });
    expect(locked.has("financials")).toBe(false);
  });
});
