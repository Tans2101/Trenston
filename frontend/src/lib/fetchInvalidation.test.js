/**
 * @jest-environment node
 */
import { fetchPathsToInvalidate } from "./fetchInvalidation";

describe("fetchPathsToInvalidate", () => {
  test("ignores GET", () => {
    expect(fetchPathsToInvalidate("get", "/production/work-orders")).toEqual([]);
  });

  test("maps production write to list prefixes", () => {
    const paths = fetchPathsToInvalidate("POST", "/production/work-orders");
    expect(paths).toContain("/production/work-orders");
    expect(paths).toContain("/me/work-items");
    expect(paths).toContain("/calendar");
  });

  test("maps deal patch", () => {
    const paths = fetchPathsToInvalidate("patch", "/deals/deal_abc");
    expect(paths).toContain("/deals");
    expect(paths).toContain("/briefing");
  });

  test("maps sales target put to order book", () => {
    const paths = fetchPathsToInvalidate("PUT", "/sales/targets");
    expect(paths).toContain("/sales/order-book");
    expect(paths).toContain("/briefing");
  });

  test("maps maintenance settings write", () => {
    const paths = fetchPathsToInvalidate("PUT", "/maintenance/settings");
    expect(paths).toContain("/maintenance/tickets");
    expect(paths).toContain("/maintenance/settings");
  });

  test("maps delegates assign to briefing/decisions/tasks", () => {
    const paths = fetchPathsToInvalidate("POST", "/delegates/suggestions/sug_1/assign");
    expect(paths).toContain("/briefing");
    expect(paths).toContain("/decisions");
    expect(paths).toContain("/tasks");
    expect(paths).toContain("/me/work-items");
  });
});
