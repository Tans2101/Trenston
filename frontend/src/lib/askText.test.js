import { parseAskBlocks, parseAskInline, askPlainText, askTaskTitle } from "./askText";

describe("Ask Trenston answer formatting", () => {
  test("paragraphs and bullet lists become separate blocks", () => {
    const blocks = parseAskBlocks("Runway is short.\n\n- Cut ads\n- Chase invoices\n\n1. First\n2. Second");
    expect(blocks.map((b) => b.type)).toEqual(["p", "ul", "ol"]);
    expect(blocks[1].items).toEqual(["Cut ads", "Chase invoices"]);
  });

  test("bold, italic and code become runs without the markers", () => {
    const runs = parseAskInline("Runway is **4.2 months**, _roughly_ and `MRR` is up");
    expect(runs.filter((r) => r.bold).map((r) => r.text)).toEqual(["4.2 months"]);
    expect(runs.filter((r) => r.italic).map((r) => r.text)).toEqual(["roughly"]);
    expect(runs.filter((r) => r.code).map((r) => r.text)).toEqual(["MRR"]);
  });

  test("underscores inside words and lone asterisks stay as text", () => {
    const runs = parseAskInline("Check snake_case_name and 3 * 4");
    expect(runs).toEqual([{ text: "Check snake_case_name and 3 * 4" }]);
  });

  test("the interrupted note renders as italic", () => {
    const blocks = parseAskBlocks("Partial answer\n\n_(Response interrupted. Please ask again.)_");
    const runs = parseAskInline(blocks[1].lines[0]);
    expect(runs[0]).toEqual({ text: "(Response interrupted. Please ask again.)", italic: true });
  });

  test("plain text and task titles drop the formatting", () => {
    const text = "**Chase the Acme invoice first.** It is 40 days late.\n\n- Call today";
    expect(askPlainText(text)).toBe("Chase the Acme invoice first. It is 40 days late.\n\n- Call today");
    expect(askTaskTitle(text)).toBe("Chase the Acme invoice first.");
  });
});
