import Briefing from "@/pages/Briefing";
import MyDay from "@/pages/MyDay";
import { useAuth } from "@/context/AuthContext";
import { isLeader } from "@/lib/access";

/**
 * One Home page that changes by role.
 * Leaders (owner, executive): the company briefing first (summary, what changed,
 * what to decide, what to hand off), then their own work below.
 * Everyone else: their own day (work across departments, decisions they can act on,
 * notes, tasks, and team update).
 * Open decisions appear once: in the briefing for leaders, in "Needs your call" for others.
 */
export default function Home() {
  const { user } = useAuth();
  if (!isLeader(user)) return <MyDay />;
  return (
    <div className="max-w-6xl" data-testid="home-leader">
      <Briefing asHome />
      <MyDay embedded hideNeedsCall />
    </div>
  );
}
