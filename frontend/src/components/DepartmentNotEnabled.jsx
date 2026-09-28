import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useDepartmentsQuery, useInvalidateDepartments } from "@/hooks/useDepartmentsQuery";
import { PageHeader, EmptyState, GlassCard } from "@/components/kit";
import { departmentIcon } from "@/lib/departmentIcons";
import { MANAGE_DEPARTMENTS_HREF } from "@/lib/departmentRoutes";

/**
 * "Department not enabled" state with a one-click Enable for anyone allowed to
 * manage departments (CEO / can_manage), and a clear ask-your-CEO path for
 * everyone else. Shared by DepartmentPlaceholder and every dedicated
 * department page so a deep link into a disabled department never dead-ends.
 *
 * Props:
 *   deptType  catalog type, e.g. "legal"
 *   label     fallback display name when the catalog has none
 *   onEnabled called after a successful enable (e.g. the page's reload).
 *             Defaults to a full reload of the current URL, which keeps any
 *             deep-link params (?item=, ?tab=, #hash).
 *   onRetry   optional "Try again" handler
 */
export default function DepartmentNotEnabled({ deptType, label, onEnabled, onRetry }) {
  const { data: catalog, reload: reloadCatalog } = useDepartmentsQuery();
  const invalidateDepartments = useInvalidateDepartments();
  const [enabling, setEnabling] = useState(false);

  const entry = (catalog?.departments || []).find((d) => d.type === deptType);
  const name = entry?.name || label || deptType?.replace(/_/g, " ") || "Department";
  const canManage = Boolean(catalog?.can_manage || catalog?.is_ceo);
  const Icon = departmentIcon(entry?.icon);

  const enableHere = async () => {
    if (!deptType) return;
    setEnabling(true);
    try {
      await api.post("/departments", { type: deptType });
      toast.success(`${name} enabled`);
      // Refresh the sidebar's department list so the nav picks it up.
      try {
        await invalidateDepartments();
      } catch {
        /* nav refresh is best-effort */
      }
      if (onEnabled) {
        await onEnabled();
        setEnabling(false);
      } else {
        window.location.assign(`${window.location.pathname}${window.location.search}${window.location.hash}`);
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not enable department");
      setEnabling(false);
      reloadCatalog();
    }
  };

  return (
    <div data-testid={`dept-not-enabled-${deptType || "unknown"}`}>
      <PageHeader title={name} subtitle="Not enabled for this company" />
      <GlassCard className="p-8">
        <EmptyState
          icon={Icon}
          title={`${name} isn’t enabled yet`}
          body={
            canManage
              ? "Enable this department to open its tools. Founders and CEOs can turn on any catalog department. Industry choice doesn’t restrict this."
              : "This department isn’t enabled for your company. Ask your founder or CEO to enable it from Account settings → Manage departments."
          }
          action={(
            <div className="flex flex-wrap items-center justify-center gap-3">
              {canManage && (
                <button
                  type="button"
                  data-testid="enable-department-here-btn"
                  disabled={enabling}
                  onClick={enableHere}
                  className="rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-4 py-2.5 hover:bg-helm-gold-hover disabled:opacity-60"
                >
                  {enabling ? "Enabling…" : `Enable ${name}`}
                </button>
              )}
              <Link
                to={MANAGE_DEPARTMENTS_HREF}
                data-testid="manage-departments-link"
                className="rounded-md border border-helm-line text-helm-fg text-sm px-4 py-2.5 hover:border-helm-gold/35"
              >
                Manage departments
              </Link>
              {onRetry && (
                <button
                  type="button"
                  onClick={onRetry}
                  className="text-sm text-helm-muted hover:text-helm-fg"
                >
                  Try again
                </button>
              )}
            </div>
          )}
        />
      </GlassCard>
    </div>
  );
}
