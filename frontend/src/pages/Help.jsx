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
    <div className="min-h-screen bg-mk-black text-white overflow-x-hidden">
      <MarketingNav authed={authed} onEnter={enter} active="/help" />

      <section className="px-6 pt-28 md:pt-36 pb-8">
        <div className="mx-auto max-w-5xl">
          <p className="font-mono text-xs uppercase tracking-[0.3em] text-[#D4B45C]">{CATEGORY}</p>
          <h1 className="font-display mt-4 text-5xl md:text-6xl font-medium tracking-[-0.03em] leading-[1.05]">
            Help
          </h1>
          <p className="mt-4 max-w-2xl text-lg text-mk-gray-dark leading-relaxed">
            New to Trenston? Start here. This page explains what the product does, what each part is for, and how owners and invited teammates use it differently.
          </p>
        </div>
      </section>

      <section className="px-6 pb-16 border-t border-white/10 pt-10">
        <div className="mx-auto max-w-5xl">
          <TrenstonHowToUse />
        </div>
      </section>

      <MarketingFooter />
    </div>
  );
}
