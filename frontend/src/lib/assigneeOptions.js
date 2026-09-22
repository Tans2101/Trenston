/**
 * Build assignee/owner dropdown options so the current user appears once as
 * "Me – [name]", and every other member by their actual name.
 */
export function memberDisplayName(m) {
  if (!m) return "";
  return (m.name || m.email || "Teammate").trim();
}

export function meAssigneeLabel(m) {
  const name = memberDisplayName(m);
  return name ? `Me – ${name}` : "Me";
}

/**
 * @param {Array} members - from GET /members (or similar)
 * @param {string|null|undefined} myUserId
 * @param {{
 *   unassigned?: boolean,
 *   unassignedLabel?: string,
 *   /** When true, Me option value is the user's id (edit forms). When false, value is "" (create default-to-me). */
 *   selfUsesId?: boolean,
 * }} [opts]
 */
export function buildAssigneeOptions(members = [], myUserId, opts = {}) {
  const {
    unassigned = false,
    unassignedLabel = "Unassigned",
    selfUsesId = false,
  } = opts;

  const active = (members || []).filter((m) => m?.user_id && m.status !== "invited");
  const self = active.find((m) => m.is_self || (myUserId && m.user_id === myUserId));
  const others = active.filter((m) => !(self && m.user_id === self.user_id) && !(myUserId && m.user_id === myUserId));

  const options = [];
  if (unassigned) {
    options.push({ value: "", label: unassignedLabel, isSelf: false });
  }

  if (self) {
    options.push({
      value: selfUsesId ? self.user_id : "",
      label: meAssigneeLabel(self),
      isSelf: true,
      user_id: self.user_id,
    });
  } else if (!unassigned) {
    options.push({ value: "", label: "Me", isSelf: true });
  }

  for (const m of others) {
    options.push({
      value: m.user_id,
      label: memberDisplayName(m),
      isSelf: false,
      user_id: m.user_id,
    });
  }
  return options;
}
