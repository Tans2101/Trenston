/**
 * @jest-environment node
 */
import { readFileSync } from "fs";
import { join } from "path";
import { PUBLIC_LINKEDIN_URL } from "./marketingCopy";

describe("organization schema", () => {
  const html = readFileSync(join(__dirname, "../../index.html"), "utf8");
  const ld = JSON.parse(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/.exec(html)[1]);
  const org = ld["@graph"].find((n) => n["@type"] === "Organization");

  test("lists the company LinkedIn page and Instagram as sameAs", () => {
    expect(org.sameAs).toContain(PUBLIC_LINKEDIN_URL);
    expect(org.sameAs).toContain("https://www.instagram.com/usetrenston/");
  });
});
