import { DEFAULT_TIMEZONE } from "@/lib/dates";

function hourInTz(now, tz) {
  const name = (tz || "").trim() || DEFAULT_TIMEZONE;
  try {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone: name,
      hour: "numeric",
      hourCycle: "h23",
    }).formatToParts(now);
    const h = Number(parts.find((p) => p.type === "hour")?.value);
    return Number.isFinite(h) ? h : now.getHours();
  } catch {
    return now.getHours();
  }
}

/** Greeting for the signed-in experience. Briefing is always just "Briefing" — never time-boxed.
 * Pass workspace IANA ``tz`` so morning/afternoon/evening match company settings, not the browser.
 */
export function dayPartGreeting(now = new Date(), tz) {
  const h = tz ? hourInTz(now, tz) : now.getHours();
  let greeting = "Hello";
  if (h >= 5 && h < 12) greeting = "Good morning";
  else if (h >= 12 && h < 17) greeting = "Good afternoon";
  else if (h >= 17 && h < 22) greeting = "Good evening";
  return { greeting, briefingLabel: "Briefing" };
}
