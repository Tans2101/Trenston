import { findVisible, placeCard } from "@/components/guide/TourOverlay";

const view = { w: 1280, h: 800 };

describe("placeCard", () => {
  it("goes below the target when there is room", () => {
    const p = placeCard({ top: 100, bottom: 140, left: 500, width: 200, height: 40 }, { h: 180 }, view);
    expect(p.top).toBe(140 + 6 + 12);
    expect(p.left).toBe(600 - 170);
  });

  it("goes above when the target is near the bottom", () => {
    const p = placeCard({ top: 700, bottom: 740, left: 500, width: 200, height: 40 }, { h: 180 }, view);
    expect(p.top).toBe(700 - 6 - 12 - 180);
  });

  it("never leaves the screen sideways", () => {
    const right = placeCard({ top: 100, bottom: 140, left: 1250, width: 30, height: 40 }, { h: 180 }, view);
    expect(right.left + right.width).toBeLessThanOrEqual(1280 - 16);
    const left = placeCard({ top: 100, bottom: 140, left: 0, width: 30, height: 40 }, { h: 180 }, view);
    expect(left.left).toBe(16);
  });

  it("centres when there is nothing to point at", () => {
    const p = placeCard(null, { h: 200 }, view);
    expect(p.left).toBe((1280 - 340) / 2);
    expect(p.top).toBe(300);
  });

  it("docks to the bottom on phones, or the top when the target is low", () => {
    const phone = { w: 390, h: 800 };
    const high = placeCard({ top: 100, bottom: 140, left: 10, width: 100, height: 40 }, { h: 200 }, phone);
    expect(high).toMatchObject({ docked: true, left: 16, width: 358, top: 800 - 200 - 16 });
    const low = placeCard({ top: 600, bottom: 640, left: 10, width: 100, height: 40 }, { h: 200 }, phone);
    expect(low.top).toBe(16);
  });
});

describe("findVisible", () => {
  afterEach(() => { document.body.innerHTML = ""; });

  it("skips hidden copies and returns the first visible match in selector order", () => {
    document.body.innerHTML = `
      <button data-testid="a" style="display:none"></button>
      <button data-testid="b"></button>`;
    const [hidden, shown] = document.querySelectorAll("button");
    hidden.getBoundingClientRect = () => ({ width: 0, height: 0 });
    shown.getBoundingClientRect = () => ({ width: 50, height: 20 });
    expect(findVisible(['[data-testid="a"]', '[data-testid="b"]'])).toBe(shown);
  });

  it("returns null when nothing matches, and survives bad selectors", () => {
    expect(findVisible(['[data-testid="nope"]'])).toBeNull();
    expect(findVisible(["[[bad"])).toBeNull();
    expect(findVisible([])).toBeNull();
  });
});
