import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

const mockFetch = jest.fn();
jest.mock("@/hooks/useFetch", () => ({
  useFetch: (...args) => mockFetch(...args),
  fetchErrorMessage: (e) => e?.message || "error",
}));
jest.mock("@/lib/api", () => ({
  api: { get: jest.fn(), post: jest.fn(), patch: jest.fn(), delete: jest.fn() },
  apiErrorMessage: (e, fallback) => fallback,
}));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));

// eslint-disable-next-line import/first
import Automations from "@/pages/Automations";

const payload = {
  max_rules: 25,
  can_see_finance: true,
  members: [{ user_id: "u1", name: "Ann" }],
  catalog: {
    signals: [{ type: "overdue_work_order", label: "A work order is overdue", financial: false }],
    metrics: [{ metric: "runway_months_below", label: "Cash runway falls below a number of months" }],
  },
  templates: [{ id: "t1", name: "Overdue work order, make a task", blurb: "Never miss one.", trigger: {}, action: {} }],
  rules: [{
    id: "r1", name: "Late orders", enabled: true, fire_count: 2, last_fired_at: "2026-10-13T08:00:00Z",
    trigger: { type: "signal", signal_type: "overdue_work_order", min_severity: "low" },
    action: { type: "create_task", priority: "High", due_in_days: 1, assignee_user_id: "u1" },
  }],
  alerts: [{ id: "a1", title: "Revenue down 60% in 2026-09", detail: "Check for missing entries.", severity: "high" }],
  events: [{
    id: "e1", summary: "WO-1 is late", rule_name: "Late orders", task_id: "t_1",
    assignee_name: "Ann", created_at: "2026-10-13T08:00:00Z",
  }],
};

const hook = (data, extra = {}) => ({ data, loading: false, error: null, reload: jest.fn(), ...extra });

describe("Automations page", () => {
  it("renders rules, alerts, templates and activity", () => {
    mockFetch.mockReturnValue(hook(payload));
    const html = renderToStaticMarkup(<Automations />);
    expect(html).toContain("Late orders");
    expect(html).toContain("a work order is overdue");
    expect(html).toContain("create a high-priority task for ann, due in 1 day");
    expect(html).toContain("Revenue down 60% in 2026-09");
    expect(html).toContain("Overdue work order, make a task");
    expect(html).toContain("WO-1 is late");
    expect(html).toContain("Ran 2 times");
  });

  it("hides money alerts when the owner cannot see finances", () => {
    mockFetch.mockReturnValue(hook({ ...payload, can_see_finance: false, alerts: [] }));
    const html = renderToStaticMarkup(<Automations />);
    expect(html).not.toContain("Anomaly alerts");
    expect(html).toContain("Your rules");
  });

  it("renders the empty state without crashing", () => {
    mockFetch.mockReturnValue(hook({ ...payload, rules: [], events: [], alerts: [], templates: [] }));
    const html = renderToStaticMarkup(<Automations />);
    expect(html).toContain("No rules yet");
    expect(html).toContain("Nothing unusual found");
  });

  it("shows a loading skeleton and a readable error", () => {
    mockFetch.mockReturnValue(hook(null, { loading: true }));
    expect(renderToStaticMarkup(<Automations />)).toContain("Automations");
    mockFetch.mockReturnValue(hook(null, { error: { message: "Only the workspace owner can manage automations" } }));
    expect(renderToStaticMarkup(<Automations />)).toContain("Only the workspace owner can manage automations");
  });
});
