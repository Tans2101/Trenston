import { Gauge } from "lucide-react";
import { AppPageHeader, EmptyState, ErrorScreen, SkeletonKPIRow, SkeletonChart } from "@/components/kit";
import { useFetch } from "@/hooks/useFetch";
import { friendlyRequestError } from "@/lib/friendlyErrors";
import WidgetGrid from "@/components/custom/WidgetGrid";

function updatedLabel(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return `Layout updated ${d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}`;
}

export default function CustomDashboard() {
  const { data, loading, error, reload } = useFetch("/custom-dashboard");

  if (loading && !data) {
    return (
      <div className="space-y-6" data-testid="custom-dashboard-loading">
        <SkeletonKPIRow count={3} />
        <SkeletonChart />
      </div>
    );
  }
  if (error) {
    if (error?.response?.status === 404) {
      return (
        <EmptyState
          icon={Gauge}
          title="No custom dashboard here"
          body="This company does not have a custom dashboard, or your email is not on its approved list. Ask your company owner."
        />
      );
    }
    return <ErrorScreen label="Custom dashboard" message={friendlyRequestError(error)} onRetry={reload} />;
  }

  const widgets = data?.widgets || [];
  return (
    <div data-testid="custom-dashboard">
      <AppPageHeader
        title={data?.title || "Custom dashboard"}
        subtitle={data?.subtitle || `Built for ${data?.company || "your company"} by Trenston.`}
        action={<span className="text-xs text-helm-muted">{updatedLabel(data?.updated_at)}</span>}
      />
      {widgets.length ? (
        <WidgetGrid widgets={widgets} />
      ) : (
        <EmptyState
          icon={Gauge}
          title="Your dashboard is being built"
          body="We are setting up your views. They will appear here as soon as they are ready."
        />
      )}
    </div>
  );
}
