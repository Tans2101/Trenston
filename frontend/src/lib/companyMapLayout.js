/**
 * Fixed layout for the company map: Cash in the middle, money in on the left,
 * money out on the right, promises underneath, the team on top, and problems in
 * a row between the money and the promises. Positions depend only on the nodes,
 * so the picture is the same every time you open it.
 */

export const NODE_SIZE = {
  cash: { w: 200, h: 68 },
  hub: { w: 116, h: 40 },
  leaf: { w: 132, h: 46 },
  problem: { w: 114, h: 52 },
  person: { w: 114, h: 46 },
};

const CASH = { x: 500, y: 300 };
const IN_HUB = { x: 232, y: 300 };
const OUT_HUB = { x: 768, y: 300 };
const IN_LEAF_X = 68;
const OUT_LEAF_X = 932;
const SIDE_TOP = 96;
const SIDE_BOTTOM = 384;
const PROBLEM_Y = 452;
const PROMISE_HUB = { x: 500, y: 560 };
const PROMISE_ROWS = [660, 724];
const PEOPLE_HUB = { x: 500, y: 130 };
const PEOPLE_ROW = 44;

function sizeOf(node) {
  if (node.kind === "cash") return NODE_SIZE.cash;
  if (node.kind === "hub") return NODE_SIZE.hub;
  if (node.kind === "problem") return NODE_SIZE.problem;
  if (node.kind === "person") return NODE_SIZE.person;
  return NODE_SIZE.leaf;
}

/** Spread `count` items across [min, max] on one axis, centred. */
function spread(count, min, max) {
  if (count <= 0) return [];
  if (count === 1) return [(min + max) / 2];
  const step = (max - min) / (count - 1);
  return Array.from({ length: count }, (_, i) => min + i * step);
}

function rowX(count, perRow, width) {
  const span = Math.min(count, perRow);
  const gap = width + 6;
  const total = gap * (span - 1);
  return Array.from({ length: span }, (_, i) => 500 - total / 2 + i * gap);
}

/** @returns {{ pos: Record<string, {x:number,y:number,w:number,h:number}>, viewBox: string, width: number, height: number }} */
export function layoutMap(nodes) {
  const pos = {};
  const place = (node, x, y) => {
    const { w, h } = sizeOf(node);
    pos[node.id] = { x, y, w, h };
  };
  const group = (g) => nodes.filter((n) => n.group === g && n.kind !== "hub" && n.kind !== "cash");
  const hub = (g) => nodes.find((n) => n.kind === "hub" && n.group === g);

  const cash = nodes.find((n) => n.kind === "cash");
  if (cash) place(cash, CASH.x, CASH.y);

  const inHub = hub("in");
  if (inHub) place(inHub, IN_HUB.x, IN_HUB.y);
  const outHub = hub("out");
  if (outHub) place(outHub, OUT_HUB.x, OUT_HUB.y);

  const inLeaves = group("in");
  spread(inLeaves.length, SIDE_TOP, SIDE_BOTTOM).forEach((y, i) => place(inLeaves[i], IN_LEAF_X, y));
  const outLeaves = group("out");
  spread(outLeaves.length, SIDE_TOP, SIDE_BOTTOM).forEach((y, i) => place(outLeaves[i], OUT_LEAF_X, y));

  const promisesHub = hub("promises");
  if (promisesHub) place(promisesHub, PROMISE_HUB.x, PROMISE_HUB.y);
  const promises = group("promises");
  const perRow = Math.ceil(promises.length / (promises.length > 6 ? 2 : 1)) || 1;
  promises.forEach((n, i) => {
    const row = Math.floor(i / perRow);
    const inRow = promises.slice(row * perRow, row * perRow + perRow);
    const xs = rowX(inRow.length, perRow, NODE_SIZE.leaf.w);
    place(n, xs[i - row * perRow], PROMISE_ROWS[Math.min(row, PROMISE_ROWS.length - 1)]);
  });

  const peopleHub = hub("people");
  if (peopleHub) place(peopleHub, PEOPLE_HUB.x, PEOPLE_HUB.y);
  const people = group("people");
  const px = rowX(people.length, 8, NODE_SIZE.person.w);
  people.forEach((n, i) => place(n, px[i], PEOPLE_ROW));

  const problems = group("problems");
  const prx = rowX(problems.length, 8, NODE_SIZE.problem.w);
  problems.forEach((n, i) => place(n, prx[i], PROBLEM_Y));

  const boxes = Object.values(pos);
  const top = boxes.length ? Math.min(...boxes.map((b) => b.y - b.h / 2)) - 18 : 0;
  const bottom = boxes.length ? Math.max(...boxes.map((b) => b.y + b.h / 2)) + 18 : 400;
  const left = 0;
  const width = 1000;
  const height = Math.max(bottom - top, 200);
  return { pos, viewBox: `${left} ${Math.round(top)} ${width} ${Math.round(height)}`, width, height };
}

/** A gentle curve from the edge of one box toward the other's centre. */
export function linkPath(a, b) {
  if (!a || !b) return "";
  const horizontal = Math.abs(b.x - a.x) >= Math.abs(b.y - a.y);
  const start = horizontal
    ? { x: a.x + Math.sign(b.x - a.x) * (a.w / 2), y: a.y }
    : { x: a.x, y: a.y + Math.sign(b.y - a.y) * (a.h / 2) };
  const end = horizontal
    ? { x: b.x - Math.sign(b.x - a.x) * (b.w / 2), y: b.y }
    : { x: b.x, y: b.y - Math.sign(b.y - a.y) * (b.h / 2) };
  const mx = (start.x + end.x) / 2;
  const my = (start.y + end.y) / 2;
  return horizontal
    ? `M ${start.x} ${start.y} C ${mx} ${start.y}, ${mx} ${end.y}, ${end.x} ${end.y}`
    : `M ${start.x} ${start.y} C ${start.x} ${my}, ${end.x} ${my}, ${end.x} ${end.y}`;
}

export function truncate(text, max) {
  const t = String(text || "");
  return t.length > max ? `${t.slice(0, Math.max(0, max - 1)).trimEnd()}…` : t;
}
