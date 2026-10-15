import { shouldRetryQuery } from "@/lib/queryClient";

const err = (status) => ({ response: { status } });

describe("shouldRetryQuery", () => {
  it("never retries access, not-found or bad-input errors", () => {
    [400, 401, 403, 404, 422].forEach((s) => expect(shouldRetryQuery(0, err(s))).toBe(false));
  });
  it("retries timeouts, rate limits, server errors and network blips up to 3 times", () => {
    [408, 429, 500, 502].forEach((s) => expect(shouldRetryQuery(0, err(s))).toBe(true));
    expect(shouldRetryQuery(0, new Error("Network Error"))).toBe(true);
    expect(shouldRetryQuery(3, err(500))).toBe(false);
  });
});
