/**
 * The core lanes every founder sees (whatever their industry) must not frame
 * the product around one industry. Optional department pages are exempt.
 */
const fs = require("fs");
const path = require("path");

const read = (rel) => fs.readFileSync(path.join(__dirname, rel), "utf8");

const CORE_LANE_FILES = [
  "Briefing.jsx",
  "MyDay.jsx",
  "Tasks.jsx",
  "Decisions.jsx",
  "Telemetry.jsx",
  "Financials.jsx",
  "Pipeline.jsx",
  "Onboarding.jsx",
  "AccountSettings.jsx",
  "../components/SalesOrderBook.jsx",
];

describe("core lane copy is industry-neutral", () => {
  it.each(CORE_LANE_FILES)("%s does not name the old robotics sample company", (file) => {
    expect(read(file)).not.toMatch(/Northwind|Robotics/);
  });

  it("My Day's empty work feed does not lead with an optional department", () => {
    expect(read("MyDay.jsx")).not.toMatch(/When Production/);
  });

  it("the order book speaks of customers and products or services, not only buyers of goods", () => {
    const src = read("../components/SalesOrderBook.jsx");
    expect(src).toContain('["buyer_name", "Customer"]');
    expect(src).toContain('["product", "Product / service"]');
    expect(src).not.toMatch(/>Buyer</);
  });

  it("the won-deal work order prompt only opens when the server offers it", () => {
    // Server sets production_prompt only when the Production department is enabled.
    expect(read("Pipeline.jsx")).toMatch(/res\?\.production_prompt && res\?\.production_prefill/);
  });
});
