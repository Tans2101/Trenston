import { Navigate, useParams } from "react-router-dom";
import { useFetch, fetchErrorMessage } from "@/hooks/useFetch";
import DepartmentNotEnabled from "@/components/DepartmentNotEnabled";
import { PageHeader, ErrorScreen, EmptyState, GlassCard, PageHeaderSkeleton, SkeletonCardList } from "@/components/kit";
import { departmentIcon } from "@/lib/departmentIcons";
import { DEPARTMENT_ROUTES } from "@/lib/departmentRoutes";

export default function DepartmentPlaceholder() {
  const { deptType } = useParams();
  const { data, loading, error, reload } = useFetch(
    deptType ? `/departments/by-type/${encodeURIComponent(deptType)}` : null,
  );

  if (loading) {
    return (
      <div>
        <PageHeaderSkeleton />
        <SkeletonCardList count={2} />
      </div>
    );
  }

  if (error) {
    const status = error?.response?.status;
    if (status === 403) {
      return (
        <ErrorScreen
          label="Access denied"
          message="You are not a member of this department. Ask your founder or CEO to add you."
          onRetry={reload}
        />
      );
    }
    if (status === 404) {
      return (
        <DepartmentNotEnabled deptType={deptType} onEnabled={reload} onRetry={reload} />
      );
    }
    return (
      <ErrorScreen
        label="Could not load department"
        message={fetchErrorMessage(error, "Something went wrong.")}
        onRetry={reload}
      />
    );
  }

  if (!data) return null;

  const realTo = DEPARTMENT_ROUTES[data.type];
  // Dedicated routes take precedence in App.js; this catches any miss and avoids a false "coming soon".
  if (realTo) {
    return <Navigate to={realTo} replace />;
  }

  const Icon = departmentIcon(data.icon);
  const name = data.name || "Department";

  return (
    <div data-testid={`dept-placeholder-${data.type}`}>
      <PageHeader title={name} subtitle="Department workspace" />
      <GlassCard className="p-8">
        <EmptyState
          icon={Icon}
          title={`${name} coming soon`}
          body={`${name} tools are coming soon. Reach out if there's a specific workflow you want prioritized.`}
          action={(
            <a
              href={`mailto:contact@trenston.com?subject=${encodeURIComponent(`${name} workflow request`)}`}
              data-testid="dept-placeholder-contact"
              className="inline-flex items-center gap-1.5 rounded-md border border-helm-line text-helm-fg text-sm px-4 py-2 hover:bg-helm-fg/[0.04]"
            >
              Request a workflow
            </a>
          )}
        />
      </GlassCard>
    </div>
  );
}
