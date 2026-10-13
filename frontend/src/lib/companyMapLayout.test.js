import { layoutMap, linkPath, truncate } from "@/lib/companyMapLayout";

const mk = (group, kind, n, prefix) => Array.from({ length: n }, (_, i) => ({ id: `${prefix}${i}`, group, kind, label: "x" }));

function fullMap() {
  return [
    { id: "cash", kind: "cash", group: "cash" },
    { id: "in", kind: "hub", group: "in" }, ...mk("in", "income", 5, "in:"), { id: "pipeline", kind: "pipeline", group: "in" },
    { id: "out", kind: "hub", group: "out" }, ...mk("out", "expense", 6, "out:"),
    { id: "promises", kind: "hub", group: "promises" }, ...mk("promises", "task", 12, "task:"),
    { id: "people", kind: "hub", group: "people" }, ...mk("people", "person", 8, "person:"),
    ...mk("problems", "problem", 8, "problem:"),
  ];
}

const overlap = (a, b) => Math.abs(a.x - b.x) < (a.w + b.w) / 2 && Math.abs(a.y - b.y) < (a.h + b.h) / 2;

describe("layoutMap", () => {
  it("places every node and never lets two overlap, even when full", () => {
    const nodes = fullMap();
    const { pos } = layoutMap(nodes);
    expect(Object.keys(pos).sort()).toEqual(nodes.map((n) => n.id).sort());
    const boxes = Object.entries(pos);
    for (let i = 0; i < boxes.length; i += 1) {
      for (let j = i + 1; j < boxes.length; j += 1) {
        expect([boxes[i][0], boxes[j][0], overlap(boxes[i][1], boxes[j][1])]).toEqual([boxes[i][0], boxes[j][0], false]);
      }
    }
  });

  it("keeps everything inside the canvas", () => {
    const { pos, width } = layoutMap(fullMap());
    Object.values(pos).forEach((b) => {
      expect(b.x - b.w / 2).toBeGreaterThanOrEqual(0);
      expect(b.x + b.w / 2).toBeLessThanOrEqual(width);
    });
  });

  it("is the same every time", () => {
    expect(layoutMap(fullMap())).toEqual(layoutMap(fullMap()));
  });

  it("crops the canvas to what is there (solo, no team row)", () => {
    const solo = fullMap().filter((n) => n.group !== "people");
    const [, top] = layoutMap(solo).viewBox.split(" ").map(Number);
    const [, topFull] = layoutMap(fullMap()).viewBox.split(" ").map(Number);
    expect(top).toBeGreaterThan(topFull);
  });

  it("handles an almost empty map", () => {
    const { pos, viewBox } = layoutMap([{ id: "cash", kind: "cash", group: "cash" }]);
    expect(Object.keys(pos)).toEqual(["cash"]);
    expect(viewBox).toMatch(/^0 -?\d+ 1000 \d+$/);
  });
});

describe("helpers", () => {
  it("linkPath draws between two boxes and tolerates missing ones", () => {
    const a = { x: 100, y: 100, w: 100, h: 40 };
    const b = { x: 400, y: 120, w: 100, h: 40 };
    expect(linkPath(a, b)).toMatch(/^M 150 100 C/);
    expect(linkPath(a, undefined)).toBe("");
  });
  it("truncate", () => {
    expect(truncate("short", 10)).toBe("short");
    expect(truncate("a very long label indeed", 10)).toBe("a very lo…");
  });
});
