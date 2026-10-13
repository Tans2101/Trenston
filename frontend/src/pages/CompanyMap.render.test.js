import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const mockFetch = jest.fn();
jest.mock("react-router-dom", () => ({
  // eslint-disable-next-line react/prop-types
  Link: ({ to, children, ...rest }) => <a href={to} {...rest}>{children}</a>,
}));
jest.mock("@/hooks/useFetch", () => ({
  useFetch: (...args) => mockFetch(...args),
  fetchErrorMessage: (e) => e?.message || "error",
}));

// eslint-disable-next-line import/first
import CompanyMap from "@/pages/CompanyMap";

const hook = (data, extra = {}) => ({ data, loading: false, error: null, reload: jest.fn(), ...extra });
const render = () => renderToStaticMarkup(<CompanyMap />);

const ready = {
  ready: true, mode: "solo", missing: [{ label: "Deals you're chasing", to: "/app/sales" }],
  nodes: [
    { id: "cash", kind: "cash", group: "cash", label: "Cash", sub: "$42,000 · 7 months of runway", tone: "ok", to: "/app/financials" },
    { id: "in", kind: "hub", group: "in", label: "Money in", tone: "neutral" },
    { id: "in:0", kind: "income", group: "in", label: "Retainers", sub: "$5,000", tone: "ok" },
    { id: "out", kind: "hub", group: "out", label: "Money out", tone: "neutral" },
    { id: "out:0", kind: "expense", group: "out", label: "Salaries", sub: "$5,000", tone: "neutral" },
    { id: "promises", kind: "hub", group: "promises", label: "Promises & deadlines", tone: "neutral" },
    { id: "task:t1", kind: "task", group: "promises", label: "Pay supplier", sub: "3 days late", tone: "bad" },
    { id: "problem:0", kind: "problem", group: "problems", label: "Task overdue: Pay supplier", sub: "d", action: "Do it, move the date, or drop it.", tone: "bad" },
  ],
  links: [
    { source: "in", target: "cash", tone: "ok" }, { source: "in:0", target: "in", tone: "ok" },
    { source: "cash", target: "out", tone: "neutral" }, { source: "out", target: "out:0", tone: "neutral" },
    { source: "promises", target: "task:t1", tone: "bad" }, { source: "problem:0", target: "task:t1", tone: "bad" },
  ],
};

describe("CompanyMap page", () => {
  it("draws the map from real records and lists what needs you", () => {
    mockFetch.mockReturnValue(hook(ready));
    const html = render();
    expect(html).toContain("Company map");
    expect(html).toContain("$42,000 · 7 months of runway");
    expect(html).toContain("Retainers");
    expect(html).toContain("Pay supplier");
    expect(html).toContain("What needs you (1)");
    expect(html).toContain("Do it, move the date, or drop it.");
    expect(html).toContain("Not on the map yet");
  });

  it("with too little data it asks for facts instead of drawing anything", () => {
    mockFetch.mockReturnValue(hook({ ready: false, mode: "solo", nodes: [], links: [], missing: [{ label: "Your cash balance", to: "/app/financials" }, { label: "Tasks and deadlines", to: "/app/tasks" }] }));
    const html = render();
    expect(html).toContain("Your map starts with a few facts");
    expect(html).toContain("Your cash balance");
    expect(html).not.toContain("company-map-svg");
  });

  it("shows a skeleton while loading and an error with retry", () => {
    mockFetch.mockReturnValue(hook(null, { loading: true }));
    expect(render()).toContain("company-map-page");
    mockFetch.mockReturnValue(hook(null, { error: { message: "boom" } }));
    expect(render()).toContain("boom");
  });
});
