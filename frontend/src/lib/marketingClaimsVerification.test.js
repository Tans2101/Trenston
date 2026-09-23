/**
 * Marketing claim verification (2026-09-18).
 * Source of truth for About / pricing FAQ accuracy vs shipped product.
 * Update this file when claims or product behavior change.
 */
import {
  VALUES,
  CEO_DAY,
  PRICING_FAQ,
  FEATURE_MODULES,
  PLANS,
  paidPlanRenewalDisclosure,
  FOUNDER_NOTE,
  FOUNDER_LINKEDIN_URL,
  FOUNDER_NAME,
  FOUNDER_ROLE,
  INTEGRATIONS_SHOWCASE,
  INTEGRATIONS_PUBLIC_BLURB,
  PUBLIC_INTEGRATIONS,
} from "./marketingCopy";

describe("marketing claim verification log", () => {
  test("About Honest synthesis claims remain present", () => {
    const honest = VALUES.find((v) => v.title === "Honest synthesis");
    expect(honest.body).toContain("Add data");
    expect(honest.body).toContain("Ask Trenston");
    expect(honest.body).toContain("Decision Center");
  });

  test("pricing FAQ and Features point at /integrations as the source of truth", () => {
    const integrations = PRICING_FAQ.find((q) => q.q.includes("integrations"));
    expect(integrations.link?.to).toBe("/integrations");
    expect(integrations.a).toMatch(/Google/i);
    expect(integrations.a).toMatch(/QuickBooks/i);
    expect(integrations.a).toMatch(/Xero/i);
    expect(integrations.a).toMatch(/SAP Business One/i);
    expect(integrations.a).toMatch(/HubSpot/i);
    expect(integrations.a).toMatch(/Slack/i);
    const mod = FEATURE_MODULES.find((m) => m.title === "Integrations");
    expect(mod.body).toBe(INTEGRATIONS_PUBLIC_BLURB);
    expect(mod.link?.to).toBe("/integrations");
    expect(INTEGRATIONS_SHOWCASE.map((i) => i.name)).toEqual([
      "Google",
      "QuickBooks",
      "Xero",
      "SAP Business One",
      "HubSpot",
      "Slack",
    ]);
  });

  test("public integrations page cards stay grounded in shipped scope", () => {
    expect(PUBLIC_INTEGRATIONS.map((i) => i.id)).toEqual([
      "google",
      "quickbooks",
      "xero",
      "sap_b1",
      "hubspot",
      "slack",
    ]);
    const google = PUBLIC_INTEGRATIONS.find((i) => i.id === "google");
    expect(google.scope).toMatch(/snippet/i);
    expect(google.scope.toLowerCase()).toMatch(/not full inbox/);
    const slack = PUBLIC_INTEGRATIONS.find((i) => i.id === "slack");
    expect(slack.scope).toMatch(/webhook/i);
    expect(slack.scope.toLowerCase()).toMatch(/no oauth/);
    expect(slack.scope.toLowerCase()).toMatch(/no dms/);
    expect(slack.description.toLowerCase()).not.toMatch(/slash command/);
  });

  test("homepage Briefing stays high-level; Gmail drafts live on integrations", () => {
    const briefing = CEO_DAY.find((s) => s.title === "Briefing");
    expect(briefing.body).toMatch(/what changed/i);
    expect(briefing.body).toMatch(/decision/i);
    expect(briefing.body).toMatch(/hand off|live data/i);
    expect(briefing.body).not.toMatch(/Gmail/i);
    expect(briefing.body).not.toMatch(/draft/i);
    const google = PUBLIC_INTEGRATIONS.find((i) => i.id === "google");
    expect(google.description).toMatch(/draft/i);
  });

  test("Decision Center module copy does not claim automated outcome-landed tracking", () => {
    const decisions = FEATURE_MODULES.find((m) => m.title === "Decision Center");
    expect(decisions.body.toLowerCase()).not.toContain("actually landed");
    expect(decisions.body.toLowerCase()).toMatch(/status and owner|do not disappear/);
  });

  test("paid plan CTAs have ARL renewal disclosure; Free does not", () => {
    expect(paidPlanRenewalDisclosure(PLANS.find((p) => p.id === "free"))).toBe("");
    for (const id of ["starter", "growth", "business"]) {
      const plan = PLANS.find((p) => p.id === id);
      const text = paidPlanRenewalDisclosure(plan);
      expect(text).toMatch(/7-day free trial/);
      expect(text).toContain(`$${plan.price}/mo`);
      expect(text).toMatch(/unless you cancel before it ends/i);
      expect(text).toMatch(/Paddle customer portal/i);
      expect(text).toMatch(/Billing/i);
    }
  });

  test("founder note stays factual and short (no new personal details)", () => {
    expect(FOUNDER_NOTE).toMatch(/builds and ships Trenston himself|built Trenston himself/i);
    expect(FOUNDER_NOTE).toMatch(/no separate product team/i);
    expect(FOUNDER_NOTE.toLowerCase()).not.toMatch(/\b(age|student|family|linkedin|photo)\b/);
  });

  test("founder LinkedIn URL is a single named constant for credit + Person sameAs", () => {
    expect(FOUNDER_NAME).toBe("Tansher Dhawan");
    expect(FOUNDER_ROLE).toBe("Founder");
    expect(FOUNDER_ROLE).not.toMatch(/CEO/i);
    expect(FOUNDER_LINKEDIN_URL).toBe("https://www.linkedin.com/in/tansherdhawan/");
  });
});
