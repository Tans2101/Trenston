import { formMetrics, reportMeta, writtenAt, MAX_REPORT_METRICS } from "./Reports";
import { uploadErrorText } from "@/components/ReportsDailyDigest";

describe("Reports helpers", () => {
  test("formMetrics keeps every saved number up to the max and pads to three", () => {
    expect(formMetrics([])).toHaveLength(3);
    const five = Array.from({ length: 5 }, (_, i) => ({ label: `m${i}`, value: i }));
    const rows = formMetrics(five);
    expect(rows).toHaveLength(5);
    expect(rows[4]).toEqual({ label: "m4", value: "4" });
    expect(formMetrics(Array.from({ length: 9 }, () => ({ label: "a", value: "1" })))).toHaveLength(MAX_REPORT_METRICS);
  });
  test("reportMeta hides the old Manual placeholder", () => {
    expect(reportMeta({ type: "Sales", period: "Manual" })).toBe("Sales");
    expect(reportMeta({ type: "Sales", period: "Oct 12 to 18" })).toBe("Sales · Oct 12 to 18");
    expect(reportMeta({ type: "", period: "" })).toBe("");
  });
  test("writtenAt is empty for bad input", () => {
    expect(writtenAt(null)).toBe("");
    expect(writtenAt("nope")).toBe("");
    expect(writtenAt("2026-10-17T07:05:00Z")).toMatch(/Oct 17/);
  });
  test("uploadErrorText only shows string details", () => {
    expect(uploadErrorText({ response: { data: { detail: "Too big" } } }, "x")).toBe("Too big");
    expect(uploadErrorText({ response: { data: { detail: [{ msg: "bad" }] } } }, "fallback")).toBe("fallback");
  });
});
