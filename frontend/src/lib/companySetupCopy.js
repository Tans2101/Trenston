/** Copy and options for the post-signup company setup flow. */

export const FOUNDER_ROLES = [
  { id: "Founder", label: "Founder", hint: "You started the company and still lead it." },
  { id: "Co-founder", label: "Co-founder", hint: "You built this alongside your partner(s)." },
  { id: "CEO", label: "CEO", hint: "Chief Executive: you run the company day to day." },
  { id: "Managing Director", label: "Managing Director", hint: "You lead operations and strategy." },
  { id: "President", label: "President", hint: "You head the organization at the top level." },
];

export const COMPANY_STAGES = [
  "Just starting out",
  "Established, growing",
  "Established, stable",
  "Family-owned / multi-generation",
  "Other",
];

export const INDUSTRIES = [
  "Manufacturing",
  "Logistics",
  "Professional Services",
  "Retail",
  "Construction",
  "Food & Beverage",
  "Agriculture",
  "Family Business",
  "Healthcare",
  "Education",
  "E-commerce",
  "SaaS / Software",
  "Fintech",
  "Marketplace",
  "AI / ML",
  "Hardware / Robotics",
  "Climate / Energy",
  "Media / Content",
  "Other",
];

export const TEAM_SIZES = [
  { label: "Just me", value: 1 },
  { label: "2–5", value: 4 },
  { label: "6–15", value: 10 },
  { label: "16–40", value: 25 },
  { label: "41–100", value: 60 },
  { label: "100+", value: 120 },
];

export const SETUP_STEPS = [
  { id: "role", label: "Your role" },
  { id: "company", label: "Company" },
  { id: "team", label: "Team & context" },
  { id: "review", label: "Review" },
];
