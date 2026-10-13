/** Plain-language wording for Automations rules, alerts and activity. */

export const SEVERITY_LABEL = { low: "Low", medium: "Medium", high: "High" };

const SEVERITY_SUFFIX = { low: "", medium: " (medium or higher)", high: " (high only)" };

function formatNumber(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return String(value ?? "");
  return n.toLocaleString("en-US", { maximumFractionDigits: 2 });
}

export function describeTrigger(trigger, catalog) {
  if (!trigger) return "";
  if (trigger.type === "metric") {
    if (trigger.metric === "runway_months_below") {
      return `Cash runway falls below ${formatNumber(trigger.value)} months`;
    }
    if (trigger.metric === "cash_below") {
      return `Cash on hand falls below ${formatNumber(trigger.value)}`;
    }
    return "A number crosses your limit";
  }
  const found = (catalog?.signals || []).find((s) => s.type === trigger.signal_type);
  const label = found?.label || String(trigger.signal_type || "").replace(/_/g, " ");
  return `${label}${SEVERITY_SUFFIX[trigger.min_severity || "low"] ?? ""}`;
}

export function describeAction(action, members) {
  if (!action || action.type === "alert") return "Show an alert here";
  const who = (members || []).find((m) => m.user_id === action.assignee_user_id)?.name;
  const due = Number(action.due_in_days) || 0;
  const when = due === 0 ? "due the same day" : `due in ${due} day${due === 1 ? "" : "s"}`;
  const priority = (action.priority || "Medium").toLowerCase();
  return `Create a ${priority}-priority task for ${who || "you"}, ${when}`;
}

export function timeAgo(iso, now = Date.now()) {
  if (!iso) return "never";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "never";
  const mins = Math.max(0, Math.round((now - then) / 60000));
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}

/** Build the POST/PATCH body from the "build your own" form. */
export function ruleBodyFromForm(form) {
  const trigger = form.triggerKind === "metric"
    ? { type: "metric", metric: form.metric, value: Number(form.metricValue) }
    : { type: "signal", signal_type: form.signalType, min_severity: form.minSeverity };
  const action = form.actionType === "alert"
    ? { type: "alert" }
    : {
      type: "create_task",
      title: form.taskTitle,
      priority: form.priority,
      due_in_days: Number(form.dueDays),
      assignee_user_id: form.assigneeId || null,
    };
  return { name: form.name, enabled: true, trigger, action };
}
