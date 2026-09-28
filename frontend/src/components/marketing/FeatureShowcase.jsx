import LaptopMockup from "@/components/marketing/LaptopMockup";
import {
  ProductionScreen,
  ProcurementScreen,
  DecisionScreen,
  FinanceScreen,
  TeamScreen,
} from "@/components/marketing/ProductScreens";
import dashboardBriefing from "@/assets/marketing/dashboard-briefing.png";
import { cn } from "@/lib/utils";

/**
 * Only "Executive intelligence" has a real product screenshot (the same
 * Briefing capture used on the homepage). The other categories compose the
 * same real cockpit-surface fragments used elsewhere on the site
 * (ProductScreens) rather than a fabricated full-dashboard photo.
 */
const TAB_PANELS = {
  intelligence: { kind: "photo", src: dashboardBriefing, alt: "The Briefing screen in Trenston" },
  finance: { kind: "fragments", screens: [FinanceScreen, DecisionScreen] },
  operations: { kind: "fragments", screens: [ProductionScreen, ProcurementScreen] },
  people: { kind: "fragments", screens: [TeamScreen] },
};

/** Laptop frame showing the product surface for one feature category. */
export default function FeatureShowcase({ categoryId }) {
  const panel = TAB_PANELS[categoryId] || TAB_PANELS.intelligence;
  if (panel.kind === "photo") return <LaptopMockup src={panel.src} alt={panel.alt} />;
  return (
    <LaptopMockup>
      <div className={cn("grid w-full gap-3", panel.screens.length > 1 ? "grid-cols-2" : "mx-auto max-w-sm")}>
        {panel.screens.map((Screen, i) => (
          <Screen key={i} />
        ))}
      </div>
    </LaptopMockup>
  );
}
