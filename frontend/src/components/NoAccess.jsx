import { Link } from "react-router-dom";
import { Lock } from "lucide-react";
import { PageHeader, EmptyState } from "@/components/kit";

/**
 * Shown when someone opens a page their access pack doesn't include (deep link,
 * old bookmark, shared URL). Says who can open it instead of an endless skeleton
 * or a "Try again" error that can never succeed.
 */
export default function NoAccess({ title, who, testId = "no-access" }) {
  return (
    <div data-testid={testId}>
      <PageHeader title={title} />
      <EmptyState
        icon={Lock}
        title="This page isn't part of your access"
        body={`${who} If you need it, ask the workspace owner to change your access in Team & Access.`}
        action={(
          <Link
            to="/app"
            className="inline-flex items-center rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-4 py-2 hover:bg-helm-gold-hover"
          >
            Back to Home
          </Link>
        )}
      />
    </div>
  );
}
