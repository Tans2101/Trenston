import Briefing from "@/pages/Briefing";
import MyDay from "@/pages/MyDay";
import { useAuth } from "@/context/AuthContext";
import { useCompanyQuery } from "@/hooks/useCompanyQuery";
import { hasPerm, isLeader } from "@/lib/access";

/**
 * One Home page that changes by role.
 * Leaders (owner, executive): the company briefing first (summary, what changed,
 * what to decide, what to hand off), then their own work below.
 * Everyone else: their own day (work across departments, decisions they can act on,
 * notes, tasks, and team update).
 * Open decisions appear once: in the briefing for leaders, in "Needs your call" for others.
 *
 * While the post-setup departments/template wizard is on screen (Briefing swaps in
 * Onboarding), do not also mount My Day underneath — that stacked the wizard on
 * top of a half-loaded personal cockpit.
 */
export default function Home() {
  const { user } = useAuth();
  const { data: company } = useCompanyQuery();
  if (!isLeader(user)) return <MyDay />;
  const inOnboardingWizard =
    company?.onboarding_done === false && hasPerm(user, "workspace:edit");
  return (
    <div className="max-w-6xl" data-testid="home-leader">
      <Briefing asHome />
      {!inOnboardingWizard ? <MyDay embedded hideNeedsCall /> : null}
    </div>
  );
}
