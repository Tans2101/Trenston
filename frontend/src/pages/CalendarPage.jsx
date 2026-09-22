import { useMemo, useState } from "react";
import { toast } from "sonner";
import {
  ChevronLeft, ChevronRight, CalendarPlus, Clock, Users, Plus, X, RefreshCw, Link2,
} from "lucide-react";
import CirDeleteBtn from "@/components/CirDeleteBtn";
import { useNavigate } from "react-router-dom";
import { useFetch, fetchErrorMessage } from "@/hooks/useFetch";
import { useDepartmentsQuery } from "@/hooks/useDepartmentsQuery";
import { api } from "@/lib/api";
import { ErrorScreen, EmptyState, GlassCard, PageHeaderSkeleton, SkeletonChart, SkeletonCardList } from "@/components/kit";
import { cn } from "@/lib/utils";

function eventScopeLabel(ev) {
  if (!ev) return null;
  if (ev.scope_label) return ev.scope_label;
  if (ev.visibility === "personal") return "Personal";
  if (ev.department_name) return ev.department_name;
  if (ev.source === "deadline" && ev.type) return ev.type;
  return null;
}

const HOUR_HEIGHT = 52;
const GRID_START = 7;
const GRID_END = 20;
const DAY_LABELS = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"];

const typeBlock = {
  Sales: "bg-helm-gold/12 border-helm-gold/35 text-helm-gold",
  Internal: "bg-helm-muted/12 border-helm-muted/35 text-helm-fg",
  "1:1": "bg-helm-status-positive/12 border-helm-status-positive/35 text-helm-fg",
  Board: "bg-helm-fg/15 border-helm-fg/30 text-helm-fg",
  Decision: "bg-helm-status-negative/12 border-helm-status-negative/35 text-helm-status-negative",
  Task: "bg-helm-status-warning/12 border-helm-status-warning/35 text-helm-fg",
  Deadline: "bg-helm-status-warning/12 border-helm-status-warning/35 text-helm-fg",
  Production: "bg-helm-gold/12 border-helm-gold/35 text-helm-gold",
  Procurement: "bg-helm-status-warning/12 border-helm-status-warning/35 text-helm-fg",
  Legal: "bg-helm-fg/15 border-helm-fg/30 text-helm-fg",
  Leave: "bg-helm-status-positive/12 border-helm-status-positive/35 text-helm-fg",
};

const typeDot = {
  Sales: "bg-helm-gold",
  Internal: "bg-helm-muted",
  "1:1": "bg-helm-status-positive",
  Board: "bg-helm-fg",
  Decision: "bg-helm-status-negative",
  Task: "bg-helm-status-warning",
  Deadline: "bg-helm-status-warning",
  Production: "bg-helm-gold",
  Procurement: "bg-helm-status-warning",
  Legal: "bg-helm-fg",
  Leave: "bg-helm-status-positive",
};

function isEditableHelmEvent(ev) {
  if (!ev || ev.source !== "helm" || String(ev.id || "").startsWith("deadline_")) return false;
  if (ev.can_edit === false) return false;
  return true;
}

function pad(n) {
  return String(n).padStart(2, "0");
}

function toIsoDate(d) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function startOfWeek(d) {
  const copy = new Date(d);
  copy.setHours(0, 0, 0, 0);
  copy.setDate(copy.getDate() - copy.getDay());
  return copy;
}

function addDays(d, n) {
  const copy = new Date(d);
  copy.setDate(copy.getDate() + n);
  return copy;
}

function sameDay(a, b) {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

function parseEventStart(ev) {
  if (ev.start_at) return new Date(ev.start_at);
  if (ev.date && ev.time) return new Date(`${ev.date}T${ev.time}:00`);
  if (ev.date) return new Date(`${ev.date}T00:00:00`);
  return null;
}

function parseEventEndDay(ev) {
  if (ev.end_at) {
    const end = new Date(ev.end_at);
    return new Date(end.getFullYear(), end.getMonth(), end.getDate());
  }
  if (ev.end_date) {
    const [y, m, d] = String(ev.end_date).slice(0, 10).split("-").map(Number);
    if (y && m && d) return new Date(y, m - 1, d);
  }
  const start = parseEventStart(ev);
  if (!start) return null;
  return new Date(start.getFullYear(), start.getMonth(), start.getDate());
}

/** True when an event covers a calendar day (inclusive start–end for multi-day leave). */
function eventCoversDay(ev, day) {
  const start = parseEventStart(ev);
  if (!start) return false;
  const startDay = new Date(start.getFullYear(), start.getMonth(), start.getDate());
  const endDay = parseEventEndDay(ev) || startDay;
  const t = new Date(day.getFullYear(), day.getMonth(), day.getDate());
  return t >= startDay && t <= endDay;
}

function weekNumber(d) {
  const date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const day = date.getUTCDay() || 7;
  date.setUTCDate(date.getUTCDate() + 4 - day);
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1));
  return Math.ceil((((date - yearStart) / 86400000) + 1) / 7);
}

function formatAgendaDay(d, today) {
  const tomorrow = addDays(today, 1);
  if (sameDay(d, today)) return `TODAY · ${d.toLocaleDateString(undefined, { month: "numeric", day: "numeric", year: "2-digit" })}`;
  if (sameDay(d, tomorrow)) return `TOMORROW · ${d.toLocaleDateString(undefined, { month: "numeric", day: "numeric", year: "2-digit" })}`;
  return d.toLocaleDateString(undefined, { weekday: "long", month: "numeric", day: "numeric" }).toUpperCase();
}

function MiniMonth({ month, selected, weekDays, onSelectDay, onPrev, onNext }) {
  const year = month.getFullYear();
  const m = month.getMonth();
  const first = new Date(year, m, 1);
  const startPad = first.getDay();
  const daysInMonth = new Date(year, m + 1, 0).getDate();
  const cells = [];
  for (let i = 0; i < startPad; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(new Date(year, m, d));

  return (
    <div className="px-4 pt-4 pb-3 border-b border-helm-line">
      <div className="flex items-center justify-between mb-3">
        <button type="button" onClick={onPrev} className="p-1 text-helm-muted hover:text-helm-fg rounded" aria-label="Previous month">
          <ChevronLeft className="w-4 h-4" />
        </button>
        <p className="text-sm font-medium text-helm-fg">
          {month.toLocaleDateString(undefined, { month: "long", year: "numeric" })}
        </p>
        <button type="button" onClick={onNext} className="p-1 text-helm-muted hover:text-helm-fg rounded" aria-label="Next month">
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>
      <div className="grid grid-cols-7 gap-0.5 text-center mb-1">
        {DAY_LABELS.map((l) => (
          <span key={l} className="text-[9px] font-mono text-helm-muted">{l[0]}</span>
        ))}
      </div>
      <div className="grid grid-cols-7 gap-0.5">
        {cells.map((day, i) => {
          if (!day) return <span key={`e-${i}`} />;
          const iso = toIsoDate(day);
          const inWeek = weekDays.some((wd) => sameDay(wd, day));
          const isSelected = sameDay(day, selected);
          const isToday = sameDay(day, new Date());
          return (
            <button
              key={iso}
              type="button"
              onClick={() => onSelectDay(day)}
              className={cn(
                "relative h-7 rounded text-xs font-mono transition-colors",
                inWeek && !isSelected && "bg-helm-fg/[0.04]",
                isSelected ? "bg-helm-gold text-helm-navy font-semibold" : "text-helm-muted hover:text-helm-fg",
                isToday && !isSelected && "ring-1 ring-helm-gold/35",
              )}
            >
              {day.getDate()}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function AgendaSidebar({ events, weekDays, selectedDay, onSelectDay }) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const grouped = useMemo(() => {
    const map = new Map();
    weekDays.forEach((d) => map.set(toIsoDate(d), []));
    events.forEach((ev) => {
      weekDays.forEach((d) => {
        const key = toIsoDate(d);
        if (eventCoversDay(ev, d) && map.has(key)) map.get(key).push(ev);
      });
    });
    for (const [, list] of map) {
      list.sort((a, b) => {
        if (a.all_day && !b.all_day) return -1;
        if (!a.all_day && b.all_day) return 1;
        return (parseEventStart(a)?.getTime() || 0) - (parseEventStart(b)?.getTime() || 0);
      });
    }
    return weekDays.map((d) => ({ day: d, items: map.get(toIsoDate(d)) || [] }));
  }, [events, weekDays]);

  return (
    <div className="flex-1 overflow-y-auto px-3 py-3 space-y-4 min-h-0">
      {grouped.map(({ day, items }) => (
        <div key={toIsoDate(day)}>
          <button
            type="button"
            onClick={() => onSelectDay(day)}
            className={cn(
              "w-full text-left text-[10px] font-mono uppercase tracking-[0.15em] mb-2 px-1",
              sameDay(day, selectedDay) ? "text-helm-gold" : "text-helm-muted hover:text-helm-fg",
            )}
          >
            {formatAgendaDay(day, today)}
          </button>
          {items.length === 0 ? (
            <p className="text-xs text-helm-muted px-1 py-1">No events</p>
          ) : (
            <div className="space-y-1">
              {items.map((ev) => (
                <button
                  key={ev.id}
                  type="button"
                  onClick={() => onSelectDay(day)}
                  className="w-full flex items-start gap-2 rounded-md px-2 py-1.5 text-left hover:bg-helm-fg/[0.04] transition-colors"
                  data-testid={`agenda-${ev.id}`}
                >
                  <span className={cn("mt-1.5 w-1.5 h-1.5 rounded-full shrink-0", typeDot[ev.type] || "bg-helm-muted")} />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm text-helm-fg truncate">{ev.title}</p>
                    <p className="text-[11px] text-helm-muted">
                      {ev.all_day ? "All day" : `${ev.time || "—"} · ${ev.duration || 0}m`}
                      {eventScopeLabel(ev) ? ` · ${eventScopeLabel(ev)}` : ""}
                    </p>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function WeekGrid({ weekDays, events, selectedDay, onEventClick }) {
  const now = new Date();
  const today = new Date();
  today.setHours(0, 0, 0, 0);

  const hours = [];
  for (let h = GRID_START; h <= GRID_END; h++) hours.push(h);

  const byDay = useMemo(() => {
    const map = weekDays.map((d) => ({ day: d, timed: [], allDay: [] }));
    events.forEach((ev) => {
      weekDays.forEach((d, idx) => {
        if (!eventCoversDay(ev, d)) return;
        if (ev.all_day) map[idx].allDay.push(ev);
        else if (sameDay(d, parseEventStart(ev))) map[idx].timed.push(ev);
      });
    });
    return map;
  }, [events, weekDays]);

  const nowTop = ((now.getHours() + now.getMinutes() / 60) - GRID_START) * HOUR_HEIGHT;
  const showNowLine = now.getHours() >= GRID_START && now.getHours() <= GRID_END;

  return (
    <div className="flex-1 flex flex-col min-h-0 min-w-0">
      {/* Day headers */}
      <div className="grid border-b border-helm-line shrink-0" style={{ gridTemplateColumns: "52px repeat(7, 1fr)" }}>
        <div className="px-2 py-2 text-[10px] font-mono text-helm-muted border-r border-helm-line">
          CW {weekNumber(weekDays[0])}
        </div>
        {weekDays.map((d) => {
          const isToday = sameDay(d, today);
          const isSelected = sameDay(d, selectedDay);
          return (
            <div
              key={toIsoDate(d)}
              className={cn(
                "px-2 py-2 text-center border-r border-helm-line last:border-r-0",
                isSelected && "bg-helm-gold/12",
              )}
            >
              <p className="text-[10px] font-mono text-helm-muted">{DAY_LABELS[d.getDay()]}</p>
              <p className={cn(
                "inline-flex items-center justify-center w-8 h-8 mt-0.5 rounded-full font-mono text-lg",
                isToday ? "bg-helm-gold text-helm-navy font-semibold" : "text-helm-fg",
              )}>
                {d.getDate()}
              </p>
            </div>
          );
        })}
      </div>

      {/* All-day row */}
      <div className="grid border-b border-helm-line shrink-0 min-h-[36px]" style={{ gridTemplateColumns: "52px repeat(7, 1fr)" }}>
        <div className="px-2 py-1 text-[9px] font-mono text-helm-muted border-r border-helm-line flex items-center">all-day</div>
        {byDay.map(({ day, allDay }) => (
          <div key={toIsoDate(day)} className="px-1 py-1 border-r border-helm-line last:border-r-0 flex flex-col gap-0.5">
            {allDay.map((ev) => (
              <button
                key={ev.id}
                type="button"
                onClick={() => onEventClick?.(ev)}
                className={cn("rounded px-1.5 py-0.5 text-[10px] truncate border text-left w-full", typeBlock[ev.type] || "bg-helm-fg/10 border-helm-line text-helm-fg", isEditableHelmEvent(ev) && "cursor-pointer hover:brightness-110")}
                title={eventScopeLabel(ev) ? `${ev.title} · ${eventScopeLabel(ev)}` : ev.title}
              >
                {ev.title}
                {eventScopeLabel(ev) ? (
                  <span className="opacity-70"> · {eventScopeLabel(ev)}</span>
                ) : null}
              </button>
            ))}
          </div>
        ))}
      </div>

      {/* Time grid */}
      <div className="flex-1 overflow-y-auto min-h-0">
        <div className="grid relative" style={{ gridTemplateColumns: "52px repeat(7, 1fr)", minHeight: (GRID_END - GRID_START + 1) * HOUR_HEIGHT }}>
          {/* Hour labels */}
          <div className="border-r border-helm-line relative">
            {hours.map((h) => (
              <div
                key={h}
                className="absolute left-0 right-0 pr-2 text-right text-[10px] font-mono text-helm-muted -translate-y-2"
                style={{ top: (h - GRID_START) * HOUR_HEIGHT }}
              >
                {h === 12 ? "noon" : h < 12 ? `${h} AM` : `${h - 12} PM`}
              </div>
            ))}
          </div>

          {/* Day columns */}
          {byDay.map(({ day, timed }, colIdx) => {
            const isToday = sameDay(day, today);
            return (
              <div
                key={toIsoDate(day)}
                className={cn(
                  "relative border-r border-helm-line last:border-r-0",
                  sameDay(day, selectedDay) && "bg-helm-gold/12",
                )}
              >
                {hours.map((h) => (
                  <div
                    key={h}
                    className="border-b border-helm-fg/[0.04]"
                    style={{ height: HOUR_HEIGHT }}
                  />
                ))}

                {isToday && showNowLine && (
                  <div className="absolute left-0 right-0 z-20 pointer-events-none flex items-center" style={{ top: nowTop }}>
                    <span className="absolute -left-[52px] w-[48px] text-right text-[9px] font-mono text-helm-status-negative pr-1">
                      {now.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}
                    </span>
                    <div className="flex-1 h-px bg-helm-status-negative" />
                    <div className="w-2 h-2 rounded-full bg-helm-status-negative -ml-1" />
                  </div>
                )}

                {timed.map((ev) => {
                  const start = parseEventStart(ev);
                  if (!start) return null;
                  const startFrac = start.getHours() + start.getMinutes() / 60;
                  const durH = (ev.duration || 30) / 60;
                  const top = (startFrac - GRID_START) * HOUR_HEIGHT;
                  const height = Math.max(durH * HOUR_HEIGHT - 2, 22);
                  if (startFrac < GRID_START || startFrac > GRID_END) return null;
                  return (
                    <button
                      key={ev.id}
                      type="button"
                      data-testid={`meeting-${ev.id}`}
                      onClick={() => onEventClick?.(ev)}
                      className={cn(
                        "absolute left-1 right-1 z-10 rounded-md border px-1.5 py-1 overflow-hidden text-left shadow-sm",
                        typeBlock[ev.type] || "bg-helm-fg/10 border-helm-fg/15 text-helm-fg",
                        isEditableHelmEvent(ev) && "cursor-pointer hover:brightness-110",
                      )}
                      style={{ top: top + 1, height }}
                      title={eventScopeLabel(ev) ? `${ev.title} · ${eventScopeLabel(ev)}` : ev.title}
                    >
                      <p className="text-[11px] font-medium leading-tight truncate">{ev.title}</p>
                      <p className="text-[10px] opacity-80 truncate">
                        {ev.time}{ev.duration ? ` · ${ev.duration}m` : ""}
                        {eventScopeLabel(ev) ? ` · ${eventScopeLabel(ev)}` : ""}
                      </p>
                    </button>
                  );
                })}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

export default function CalendarPage() {
  const navigate = useNavigate();
  const [weekStart, setWeekStart] = useState(() => startOfWeek(new Date()));
  const [sidebarMonth, setSidebarMonth] = useState(() => new Date(new Date().getFullYear(), new Date().getMonth(), 1));
  const [selectedDay, setSelectedDay] = useState(() => {
    const t = new Date();
    t.setHours(0, 0, 0, 0);
    return t;
  });
  const [view, setView] = useState("week");
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({
    title: "", date: "", time: "09:00", duration: 30, type: "Internal",
    all_day: false, push_to_google: false, visibility: "personal", department_id: "",
  });
  const [busy, setBusy] = useState(false);
  const [connecting, setConnecting] = useState(false);

  const weekParam = toIsoDate(weekStart);
  const { data, loading, error, reload } = useFetch(`/calendar?week_start=${weekParam}`, [weekParam]);
  const { data: departmentsData } = useDepartmentsQuery();

  const scopeDepartments = useMemo(() => {
    const rows = departmentsData?.departments || [];
    const isCeo = departmentsData?.is_ceo === true;
    return rows.filter((d) => d.enabled && d.department_id && (isCeo || d.is_member));
  }, [departmentsData]);

  const weekDays = useMemo(() => Array.from({ length: 7 }, (_, i) => addDays(weekStart, i)), [weekStart]);
  const events = data?.events || data?.meetings || [];

  const goToday = () => {
    const t = new Date();
    t.setHours(0, 0, 0, 0);
    const ws = startOfWeek(t);
    setWeekStart(ws);
    setSelectedDay(t);
    setSidebarMonth(new Date(t.getFullYear(), t.getMonth(), 1));
  };

  const shiftWeek = (delta) => {
    setWeekStart((ws) => addDays(ws, delta * 7));
  };

  const pickDay = (day) => {
    setSelectedDay(day);
    setWeekStart(startOfWeek(day));
    setSidebarMonth(new Date(day.getFullYear(), day.getMonth(), 1));
  };

  const openAdd = (day) => {
    setEditing(null);
    setForm({
      title: "", date: toIsoDate(day || selectedDay), time: "09:00", duration: 30, type: "Internal",
      all_day: false, push_to_google: false, visibility: "personal", department_id: "",
    });
    setShowForm(true);
  };

  const openEdit = (ev) => {
    if (data?.can_write !== true || !isEditableHelmEvent(ev)) return;
    setEditing(ev.id);
    const vis = ev.visibility === "department" ? "department" : "personal";
    setForm({
      title: ev.title,
      date: ev.date || toIsoDate(selectedDay),
      time: ev.time || "09:00",
      duration: ev.duration || 30,
      type: ev.type || "Internal",
      all_day: !!ev.all_day,
      push_to_google: false,
      visibility: vis,
      department_id: vis === "department" ? (ev.department_id || "") : "",
    });
    setShowForm(true);
  };

  const submitEvent = async () => {
    if (!form.title.trim()) { toast.error("Title is required"); return; }
    if (form.visibility === "department" && !form.department_id) {
      toast.error("Choose a department for this event");
      return;
    }
    setBusy(true);
    try {
      const body = {
        title: form.title,
        date: form.date,
        time: form.time,
        duration: form.duration,
        type: form.type,
        all_day: form.all_day,
        push_to_google: form.push_to_google,
        visibility: form.visibility,
        department_id: form.visibility === "department" ? form.department_id : null,
      };
      if (editing) await api.patch(`/calendar/events/${editing}`, body);
      else await api.post("/calendar/events", body);
      toast.success(editing ? "Event updated" : "Event added");
      setShowForm(false);
      reload();
    } catch (e) { toast.error(e?.response?.data?.detail || "Could not save event"); }
    finally { setBusy(false); }
  };

  const deleteEvent = async () => {
    if (!editing || !window.confirm("Delete this event?")) return;
    setBusy(true);
    try {
      await api.delete(`/calendar/events/${editing}`);
      toast.success("Event deleted");
      setShowForm(false);
      reload();
    } catch (e) { toast.error("Could not delete"); }
    finally { setBusy(false); }
  };

  const connectGoogle = async () => {
    setConnecting(true);
    try {
      const { data: res } = await api.get("/integrations/google/connect");
      if (res.configured && res.authorization_url) {
        window.location.href = res.authorization_url;
        return;
      }
      toast.info(res.message || "Google Calendar isn't available yet. Try again later.");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not start Google Calendar connection");
    } finally {
      setConnecting(false);
    }
  };

  if (loading) {
    return (
      <div>
        <PageHeaderSkeleton className="px-2 md:px-4" />
        <div className="px-2 md:px-4 mb-4">
          <SkeletonChart />
        </div>
        <div className="px-2 md:px-4">
          <SkeletonCardList count={3} />
        </div>
      </div>
    );
  }
  if (error || !data) {
    return (
      <ErrorScreen
        label="Could not load calendar"
        message={fetchErrorMessage(error, "Calendar data is unavailable right now.")}
        onRetry={reload}
      />
    );
  }

  const hasEvents = events.length > 0;
  const canWrite = data.can_write === true;
  const googleConnected = data.google_connected || data.live || data.source === "google_calendar";
  const googleAvailable = data.google_available !== false;

  const syncBanner = !googleConnected && (
    <GlassCard className="p-4 mb-4 mx-2 md:mx-4 fade-up border-helm-gold/35" data-testid="calendar-sync-banner">
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <div className="flex-1">
          <p className="text-sm text-helm-fg font-medium">Sync your calendar</p>
          <p className="text-xs text-helm-muted mt-1 leading-relaxed">
            Connect Google Calendar to pull in your meetings and external events. Each teammate connects their own Google account. Microsoft Teams calendar sync is coming soon.
          </p>
        </div>
        <div className="flex flex-wrap gap-2 shrink-0">
          {googleAvailable ? (
            <button type="button" data-testid="connect-google-calendar-btn" onClick={connectGoogle} disabled={connecting}
              className="inline-flex items-center gap-1.5 rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-4 py-2 hover:bg-helm-gold-hover disabled:opacity-60">
              <Link2 className="w-4 h-4" />{connecting ? "Connecting…" : "Connect Google Calendar"}
            </button>
          ) : (
            <span className="text-xs text-helm-muted border border-helm-line rounded-md px-3 py-2">Google Calendar unavailable on this instance</span>
          )}
          <span className="text-xs text-helm-muted border border-helm-line rounded-md px-3 py-2">Microsoft Teams coming soon</span>
        </div>
      </div>
    </GlassCard>
  );

  if (!hasEvents && !googleConnected && !canWrite) {
    return (
      <div>
        <div className="mb-8">
          <h1 className="font-display text-3xl font-normal tracking-tight text-helm-fg">Calendar</h1>
          <p className="text-helm-muted text-sm mt-2">Week view with your meetings and Trenston deadlines.</p>
        </div>
        <EmptyState
          icon={CalendarPlus}
          title="Sync your calendar"
          body="Connect your Google Calendar to see your meetings alongside Trenston deadlines. Microsoft Teams sync is on the roadmap."
          action={googleAvailable ? (
            <button data-testid="connect-calendar-btn" onClick={connectGoogle} disabled={connecting}
              className="inline-flex items-center gap-1.5 rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-4 py-2 hover:bg-helm-gold-hover disabled:opacity-60">
              <CalendarPlus className="w-4 h-4" />{connecting ? "Connecting…" : "Connect Google Calendar"}
            </button>
          ) : (
            <button data-testid="connect-calendar-btn" onClick={() => navigate("/app/integrations")}
              className="inline-flex items-center gap-1.5 rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-4 py-2 hover:bg-helm-gold-hover">
              <CalendarPlus className="w-4 h-4" /> View integrations
            </button>
          )}
        />
      </div>
    );
  }

  return (
    <div className="fade-up -mx-2 md:-mx-4">
      {syncBanner}
      <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-4 mb-4 px-2 md:px-4">
        <div>
          <h1 className="font-display text-2xl md:text-3xl font-normal tracking-tight text-helm-fg">Calendar</h1>
          <p className="text-helm-muted text-sm mt-1">
            {googleConnected ? "Synced with your Google Calendar" : "Trenston events and deadlines. Connect your Google to sync personal meetings"}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3 text-sm">
          {!googleConnected && googleAvailable && (
            <button type="button" onClick={connectGoogle} disabled={connecting}
              className="inline-flex items-center gap-1.5 rounded-md border border-helm-gold/35 bg-helm-gold/12 text-helm-gold text-sm px-3 py-2 hover:bg-helm-gold/10 disabled:opacity-60">
              <RefreshCw className={cn("w-3.5 h-3.5", connecting && "animate-spin")} />
              {connecting ? "Connecting…" : "Sync Google Calendar"}
            </button>
          )}
          {canWrite && (
            <button type="button" data-testid="add-event-btn" onClick={() => openAdd(selectedDay)}
              className="inline-flex items-center gap-1.5 rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-3 py-2 hover:bg-helm-gold-hover">
              <Plus className="w-4 h-4" /> Add event
            </button>
          )}
          <div className="flex items-center gap-1 rounded-lg border border-helm-line bg-helm-fg/[0.02] p-1">
            <button type="button" onClick={() => shiftWeek(-1)} className="p-1.5 text-helm-muted hover:text-helm-fg rounded" aria-label="Previous week">
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button type="button" onClick={goToday} className="px-3 py-1 text-helm-fg hover:text-helm-fg font-mono text-xs uppercase tracking-wider">
              Today
            </button>
            <button type="button" onClick={() => shiftWeek(1)} className="p-1.5 text-helm-muted hover:text-helm-fg rounded" aria-label="Next week">
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
          <div className="flex rounded-lg border border-helm-line overflow-hidden">
            {["day", "week", "month"].map((v) => (
              <button
                key={v}
                type="button"
                onClick={() => setView(v)}
                className={cn(
                  "px-3 py-1.5 text-xs font-mono uppercase tracking-wider capitalize",
                  view === v ? "bg-helm-gold/12 text-helm-gold" : "text-helm-muted hover:text-helm-fg",
                )}
              >
                {v}
              </button>
            ))}
          </div>
          <div className="hidden sm:flex items-center gap-4 text-xs text-helm-muted font-mono">
            <span className="flex items-center gap-1"><Clock className="w-3.5 h-3.5 text-helm-gold" />{data.focus_hours ?? 0}h focus</span>
            <span className="flex items-center gap-1"><Users className="w-3.5 h-3.5 text-helm-gold" />{data.meeting_hours ?? 0}h meetings</span>
          </div>
        </div>
      </div>

      <div
        className="flex rounded-xl border border-helm-fg/[0.08] bg-helm-bg overflow-hidden min-h-[560px] lg:min-h-[calc(100vh-12rem)]"
        data-testid="calendar-week-layout"
      >
        <aside className="hidden md:flex w-[260px] lg:w-[280px] shrink-0 flex-col border-r border-helm-line bg-helm-bg">
          <MiniMonth
            month={sidebarMonth}
            selected={selectedDay}
            weekDays={weekDays}
            onSelectDay={pickDay}
            onPrev={() => setSidebarMonth((m) => new Date(m.getFullYear(), m.getMonth() - 1, 1))}
            onNext={() => setSidebarMonth((m) => new Date(m.getFullYear(), m.getMonth() + 1, 1))}
          />
          <AgendaSidebar events={events} weekDays={weekDays} selectedDay={selectedDay} onSelectDay={pickDay} />
        </aside>

        <div className="flex-1 flex flex-col min-w-0 bg-helm-bg">
          {view === "week" && (
            <WeekGrid weekDays={weekDays} events={events} selectedDay={selectedDay} onEventClick={openEdit} />
          )}
          {view === "day" && (
            <WeekGrid weekDays={[selectedDay]} events={events.filter((ev) => eventCoversDay(ev, selectedDay))} selectedDay={selectedDay} onEventClick={openEdit} />
          )}
          {view === "month" && (
            <div className="p-4 flex-1 overflow-auto">
              <MiniMonth
                month={sidebarMonth}
                selected={selectedDay}
                weekDays={weekDays}
                onSelectDay={(d) => { pickDay(d); setView("day"); }}
                onPrev={() => setSidebarMonth((m) => new Date(m.getFullYear(), m.getMonth() - 1, 1))}
                onNext={() => setSidebarMonth((m) => new Date(m.getFullYear(), m.getMonth() + 1, 1))}
              />
              <p className="text-sm text-helm-muted mt-4 px-4">Select a day to open the detailed schedule.</p>
            </div>
          )}
        </div>
      </div>

      {showForm && (
        <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center">
          <div className="absolute inset-0 bg-helm-ink/70" onClick={() => setShowForm(false)} />
          <GlassCard className="relative w-full sm:max-w-md m-0 sm:m-4 rounded-t-2xl sm:rounded-2xl p-6" data-testid="event-form">
            <div className="flex items-center justify-between mb-5">
              <h3 className="text-lg text-helm-fg font-light">{editing ? "Edit event" : "Add event"}</h3>
              <button onClick={() => setShowForm(false)} className="text-helm-muted hover:text-helm-fg"><X className="w-5 h-5" /></button>
            </div>
            <div className="space-y-3">
              <label className="text-xs text-helm-muted block">Title
                <input data-testid="event-title" value={form.title} onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40" />
              </label>
              <div className="grid grid-cols-2 gap-3">
                <label className="text-xs text-helm-muted">Date
                  <input type="date" data-testid="event-date" value={form.date} onChange={(e) => setForm((f) => ({ ...f, date: e.target.value }))} className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40" />
                </label>
                <label className="text-xs text-helm-muted">Type
                  <select value={form.type} onChange={(e) => setForm((f) => ({ ...f, type: e.target.value }))} className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40">
                    {["Internal", "Sales", "1:1", "Board"].map((t) => <option key={t} value={t}>{t}</option>)}
                  </select>
                </label>
              </div>
              <label className="text-xs text-helm-muted block">Visibility
                <select
                  data-testid="event-visibility"
                  value={form.visibility === "department" ? `department:${form.department_id || ""}` : "personal"}
                  onChange={(e) => {
                    const v = e.target.value;
                    if (v === "personal") {
                      setForm((f) => ({ ...f, visibility: "personal", department_id: "" }));
                    } else {
                      const deptId = v.startsWith("department:") ? v.slice("department:".length) : "";
                      setForm((f) => ({ ...f, visibility: "department", department_id: deptId }));
                    }
                  }}
                  className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40"
                >
                  <option value="personal">Personal (only me)</option>
                  {scopeDepartments.length === 0 ? (
                    <option value="department:" disabled>No departments available</option>
                  ) : (
                    scopeDepartments.map((d) => (
                      <option key={d.department_id} value={`department:${d.department_id}`}>
                        {d.name} department
                      </option>
                    ))
                  )}
                </select>
              </label>
              <label className="flex items-center gap-2 text-sm text-helm-fg">
                <input type="checkbox" checked={form.all_day} onChange={(e) => setForm((f) => ({ ...f, all_day: e.target.checked }))} className="accent-helm-gold" />
                All day
              </label>
              {!form.all_day && (
                <div className="grid grid-cols-2 gap-3">
                  <label className="text-xs text-helm-muted">Start time
                    <input type="time" value={form.time} onChange={(e) => setForm((f) => ({ ...f, time: e.target.value }))} className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40" />
                  </label>
                  <label className="text-xs text-helm-muted">Duration (min)
                    <input type="number" min={15} step={15} value={form.duration} onChange={(e) => setForm((f) => ({ ...f, duration: parseInt(e.target.value, 10) || 30 }))} className="mt-1 w-full rounded-md border border-helm-line bg-helm-card text-helm-fg text-sm px-3 py-2 focus:outline-none focus:border-helm-gold/40" />
                  </label>
                </div>
              )}
              {googleConnected && !editing && (
                <label className="flex items-center gap-2 text-sm text-helm-fg">
                  <input
                    type="checkbox"
                    data-testid="event-push-google"
                    checked={form.push_to_google}
                    onChange={(e) => setForm((f) => ({ ...f, push_to_google: e.target.checked }))}
                    className="accent-helm-gold"
                  />
                  Also add to Google Calendar
                </label>
              )}
            </div>
            <div className="flex gap-2 mt-5">
              {editing && (
                <CirDeleteBtn onClick={deleteEvent} disabled={busy} size="md" title="Delete event" data-testid="calendar-delete-event" />
              )}
              <button data-testid="submit-event-btn" onClick={submitEvent} disabled={busy} className="flex-1 rounded-md bg-helm-gold text-helm-navy font-medium py-2.5 text-sm hover:bg-helm-gold-hover disabled:opacity-60">{busy ? "Saving…" : editing ? "Save event" : "Add event"}</button>
            </div>
          </GlassCard>
        </div>
      )}
    </div>
  );
}
