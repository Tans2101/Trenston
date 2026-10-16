import { insightErrorState } from "./MoneyInsights";

jest.mock("@/lib/api", () => ({ api: { get: jest.fn(), post: jest.fn() } }));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));

test("a 503 from the server shows the maintenance message", () => {
  const err = { response: { status: 503, data: { detail: { reason: "maintenance", message: "AI summaries are under maintenance. Please try again later." } } } };
  expect(insightErrorState(err)).toEqual({
    kind: "maintenance",
    message: "AI summaries are under maintenance. Please try again later.",
  });
});

test("maintenance still shows if the server sends no message", () => {
  const out = insightErrorState({ response: { status: 503, data: {} } });
  expect(out.kind).toBe("maintenance");
  expect(out.message).toMatch(/under maintenance/i);
});

test("other failures show their own message, never a raw error", () => {
  expect(insightErrorState({ response: { status: 429, data: { detail: "Try again in a little while." } } }))
    .toEqual({ kind: "error", message: "Try again in a little while." });
  expect(insightErrorState(new Error("Network Error")).message).toMatch(/Could not write/);
});
