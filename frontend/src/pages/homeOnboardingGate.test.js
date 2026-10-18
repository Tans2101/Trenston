/**
 * Leaders must not see My Day stacked under the departments/template wizard.
 */
const fs = require("fs");
const path = require("path");

const src = fs.readFileSync(path.join(__dirname, "Home.jsx"), "utf8");

describe("Home onboarding gate", () => {
  it("skips embedded My Day while onboarding_done is false for workspace editors", () => {
    expect(src).toMatch(/onboarding_done === false/);
    expect(src).toMatch(/workspace:edit/);
    expect(src).toMatch(/!inOnboardingWizard \? <MyDay embedded hideNeedsCall \/> : null/);
  });
});
