import TrenstonHowToUse from "@/components/HelmHowToUse";
import { PageHeader } from "@/components/kit";

export default function AppHelp() {
  return (
    <div className="max-w-3xl" data-testid="app-help-page">
      <PageHeader
        title="Help"
        subtitle="New to Trenston? Start here. This page explains what the product does, what each part is for, and how owners and invited teammates use it differently."
      />
      <TrenstonHowToUse />
    </div>
  );
}
