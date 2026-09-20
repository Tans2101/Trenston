import { useEffect } from "react";
import MarketingNav from "@/components/marketing/MarketingNav";
import MarketingFooter from "@/components/marketing/MarketingFooter";
import TrenstonHowToUse from "@/components/HelmHowToUse";
import { useMarketingAuth } from "@/hooks/useMarketingAuth";
import { CATEGORY } from "@/lib/marketingCopy";

export default function Help() {
  const { authed, enter } = useMarketingAuth();
  useEffect(() => { window.scrollTo(0, 0); }, []);

  return (
    <div className="min-h-screen bg-helm-cream text-helm-navy overflow-x-hidden">
      <MarketingNav authed={authed} onEnter={enter} active="/help" />

      <section className="px-6 pt-36 md:pt-48 pb-20">
        <div className="mx-auto max-w-3xl">
          <p className="font-mono text-xs uppercase tracking-[0.3em] text-helm-slate">{CATEGORY}</p>
          <h1 className="font-display mt-8 text-5xl md:text-6xl font-medium tracking-[-0.03em] leading-[1.05]">
            Help
          </h1>
          <p className="mt-6 text-lg text-helm-slate leading-relaxed">
            New to Trenston? Start here. This page explains what the product does, what each part is for, and how owners and invited teammates use it differently.
          </p>
        </div>
      </section>

      <section className="px-6 pb-24 border-t border-helm-navy/[0.05] pt-16">
        <div className="mx-auto max-w-3xl">
          <TrenstonHowToUse />
        </div>
      </section>

      <MarketingFooter />
    </div>
  );
}
