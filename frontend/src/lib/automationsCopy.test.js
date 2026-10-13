import {
  describeAction, describeTrigger, ruleBodyFromForm, timeAgo,
} from "@/lib/automationsCopy";

const catalog = { signals: [{ type: "overdue_work_order", label: "A work order is overdue" }] };
const members = [{ user_id: "u1", name: "Ann" }];

describe("describeTrigger", () => {
  it("uses the catalog label and adds the severity floor", () => {
    expect(describeTrigger({ type: "signal", signal_type: "overdue_work_order", min_severity: "low" }, catalog))
      .toBe("A work order is overdue");
    expect(describeTrigger({ type: "signal", signal_type: "overdue_work_order", min_severity: "high" }, catalog))
      .toBe("A work order is overdue (high only)");
  });

  it("falls back to a readable name for unknown signals", () => {
    expect(describeTrigger({ type: "signal", signal_type: "some_new_signal" }, catalog)).toBe("some new signal");
  });

  it("describes money limits", () => {
    expect(describeTrigger({ type: "metric", metric: "runway_months_below", value: 6 }, catalog))
      .toBe("Cash runway falls below 6 months");
    expect(describeTrigger({ type: "metric", metric: "cash_below", value: 25000 }, catalog))
      .toBe("Cash on hand falls below 25,000");
  });
});

describe("describeAction", () => {
  it("describes tasks with who and when", () => {
    expect(describeAction({ type: "create_task", priority: "High", due_in_days: 0, assignee_user_id: "u1" }, members))
      .toBe("Create a high-priority task for Ann, due the same day");
    expect(describeAction({ type: "create_task", priority: "Low", due_in_days: 1 }, members))
      .toBe("Create a low-priority task for you, due in 1 day");
    expect(describeAction({ type: "create_task", priority: "Medium", due_in_days: 5 }, members))
      .toBe("Create a medium-priority task for you, due in 5 days");
  });

  it("describes alert-only rules", () => {
    expect(describeAction({ type: "alert" }, members)).toBe("Show an alert here");
  });
});

describe("timeAgo", () => {
  const now = new Date("2026-10-13T12:00:00Z").getTime();
  it("reads naturally", () => {
    expect(timeAgo(null, now)).toBe("never");
    expect(timeAgo("2026-10-13T11:59:40Z", now)).toBe("just now");
    expect(timeAgo("2026-10-13T11:15:00Z", now)).toBe("45 min ago");
    expect(timeAgo("2026-10-13T07:00:00Z", now)).toBe("5 h ago");
    expect(timeAgo("2026-10-10T12:00:00Z", now)).toBe("3 days ago");
  });
});

describe("ruleBodyFromForm", () => {
  const base = {
    name: "Late orders", triggerKind: "signal", signalType: "overdue_work_order", minSeverity: "medium",
    metric: "runway_months_below", metricValue: "6", actionType: "create_task",
    taskTitle: "Chase {summary}", priority: "High", dueDays: "2", assigneeId: "",
  };

  it("builds a signal + task body", () => {
    expect(ruleBodyFromForm(base)).toEqual({
      name: "Late orders", enabled: true,
      trigger: { type: "signal", signal_type: "overdue_work_order", min_severity: "medium" },
      action: { type: "create_task", title: "Chase {summary}", priority: "High", due_in_days: 2, assignee_user_id: null },
    });
  });

  it("builds a metric + alert body", () => {
    const body = ruleBodyFromForm({ ...base, triggerKind: "metric", actionType: "alert" });
    expect(body.trigger).toEqual({ type: "metric", metric: "runway_months_below", value: 6 });
    expect(body.action).toEqual({ type: "alert" });
  });
});
