import { Link, useLocation } from "react-router-dom";
import { Compass } from "lucide-react";
import { EmptyState, GlassCard } from "@/components/kit";
import MarketingNav from "@/components/marketing/MarketingNav";
import MarketingFooter from "@/components/marketing/MarketingFooter";
import { useMarketingAuth } from "@/hooks/useMarketingAuth";

export default function NotFound() {
  const { pathname } = useLocation();
  const { authed, enter } = useMarketingAuth();
  const inApp = pathname === "/app" || pathname.startsWith("/app/");
  const homeTo = authed ? "/app" : "/";
  const homeLabel = authed ? "Back to briefing" : "Back to home";

  const body = (
    <GlassCard className="p-8">
      <EmptyState
        icon={Compass}
        title="Page not found"
        body="This URL doesn't match any page in Trenston. Check the link, or head back and pick up where you left off."
        action={
          <Link
            to={homeTo}
            data-testid="not-found-home-link"
            className="inline-flex items-center rounded-md bg-helm-gold text-helm-navy font-medium text-sm px-4 py-2 hover:bg-helm-gold-hover"
          >
            {homeLabel}
          </Link>
        }
      />
    </GlassCard>
  );

  if (inApp) {
    return <div data-testid="not-found">{body}</div>;
  }

  return (
    <div className="min-h-screen bg-helm-bg text-helm-navy overflow-x-hidden flex flex-col" data-testid="not-found">
      <MarketingNav authed={authed} onEnter={enter} />
      <main className="flex-1 px-6 pt-36 md:pt-44 pb-16">
        <div className="mx-auto max-w-xl">{body}</div>
      </main>
      <MarketingFooter />
    </div>
  );
}
