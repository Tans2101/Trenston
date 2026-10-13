import { ALL_GUIDES, GUIDES, guideById, guideForPath } from "@/lib/pageGuides";
import { GLOSSARY } from "@/lib/glossary";

// Must match GUIDE_ID_RE in backend/server.py, or "seen" can't be saved.
const SERVER_ID = /^[a-z0-9][a-z0-9_-]{0,39}$/;
// Tour ids the backend checklist points at (backend/server.py onboarding_checklist).
const CHECKLIST_TOURS = ["briefing", "financials", "decisions", "quickadd", "people", "members", "myday", "tasks"];

describe("page guides", () => {
  it("every guide is complete and its id can be saved", () => {
    const ids = new Set();
    ALL_GUIDES.forEach((g) => {
      expect(g.id).toMatch(SERVER_ID);
      expect(ids.has(g.id)).toBe(false);
      ids.add(g.id);
      expect(g.name).toBeTruthy();
      expect(g.purpose.length).toBeGreaterThan(20);
      g.steps.forEach((s) => {
        expect(Array.isArray(s.targets)).toBe(true);
        expect(s.title).toBeTruthy();
        expect(s.body.length).toBeGreaterThan(15);
      });
    });
  });

  it("tours stay short", () => {
    ALL_GUIDES.forEach((g) => expect(g.steps.length).toBeLessThanOrEqual(6));
  });

  it("every checklist step has a tour to run", () => {
    CHECKLIST_TOURS.forEach((id) => expect(guideById(id)).not.toBeNull());
  });

  it("finds the guide for a page", () => {
    expect(guideForPath("/app").id).toBe("briefing");
    expect(guideForPath("/app/").id).toBe("briefing");
    expect(guideForPath("/app/me").id).toBe("myday");
    expect(guideForPath("/app/financials").id).toBe("financials");
    expect(guideForPath("/app/departments/legal").id).toBe("legal");
    expect(guideForPath("/app/map").id).toBe("map");
    expect(guideForPath("/app/settings")).toBeNull();
    expect(guideForPath("/pricing")).toBeNull();
  });

  it("only page guides have paths; quick add works anywhere", () => {
    GUIDES.forEach((g) => expect(g.path).toBeInstanceOf(RegExp));
    expect(guideById("quickadd").path).toBeUndefined();
    expect(guideById("quickadd").steps.some((s) => s.tryIt)).toBe(true);
  });

  it("does not use words people asked us to avoid", () => {
    const text = JSON.stringify(ALL_GUIDES.map(({ path, ...rest }) => rest)) + JSON.stringify(GLOSSARY);
    expect(text).not.toMatch(/commute|—/i);
  });
});
