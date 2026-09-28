import {
  REVENUE_CATEGORIES, EXPENSE_CATEGORIES, GOODS_INDUSTRIES, SERVICES_INDUSTRIES, defaultRevenueCategory,
} from "./financeCategories";
import { INDUSTRIES } from "./companySetupCopy";

describe("financeCategories", () => {
  it("offers categories for goods and service businesses, not only SaaS", () => {
    expect(REVENUE_CATEGORIES).toEqual(expect.arrayContaining(["Subscriptions", "Product sales", "Services", "Other"]));
    expect(EXPENSE_CATEGORIES).toEqual(expect.arrayContaining(["Payroll", "Cost of goods", "Cloud/Infra", "Other"]));
  });

  it("defaults the revenue category from the CompanySetup industry", () => {
    expect(defaultRevenueCategory("Manufacturing")).toBe("Product sales");
    expect(defaultRevenueCategory("E-commerce")).toBe("Product sales");
    expect(defaultRevenueCategory("Professional Services")).toBe("Services");
    expect(defaultRevenueCategory("SaaS / Software")).toBe("Subscriptions");
    expect(defaultRevenueCategory("")).toBe("Subscriptions");
    expect(defaultRevenueCategory(undefined)).toBe("Subscriptions");
  });

  it("maps every CompanySetup industry to a real dropdown option", () => {
    INDUSTRIES.forEach((ind) => {
      expect(REVENUE_CATEGORIES).toContain(defaultRevenueCategory(ind));
    });
  });

  it("only lists industries CompanySetup actually offers", () => {
    [...GOODS_INDUSTRIES, ...SERVICES_INDUSTRIES].forEach((ind) => {
      expect(INDUSTRIES).toContain(ind);
    });
  });

  it("keeps the sample workspace's industry selectable in CompanySetup", () => {
    // backend/seed_data.py sets the sample industry to this exact string.
    expect(INDUSTRIES).toContain("SaaS / Software");
  });
});
