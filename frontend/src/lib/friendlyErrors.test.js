import { friendlyRequestError, shouldReportGlobalError } from "@/lib/friendlyErrors";
import { apiErrorMessage } from "@/lib/api";
import { fetchErrorMessage } from "@/hooks/useFetch";

function axiosError({ status, detail, code, message = "Request failed" } = {}) {
  const error = new Error(message);
  error.isAxiosError = true;
  if (code) error.code = code;
  if (status) error.response = { status, data: detail === undefined ? {} : { detail } };
  return error;
}

test("server detail always wins over generic copy", () => {
  const err = axiosError({ status: 400, detail: "Pick a due date." });
  expect(apiErrorMessage(err)).toBe("Pick a due date.");
  expect(fetchErrorMessage(err)).toBe("Pick a due date.");
  expect(apiErrorMessage(axiosError({ status: 422, detail: [{ msg: "name is required" }] }))).toBe("name is required");
});

test("raw axios messages never reach the user", () => {
  const network = axiosError({ message: "Network Error", code: "ERR_NETWORK" });
  expect(apiErrorMessage(network)).toBe("Couldn't reach Trenston. Check your connection and try again.");
  const bare500 = axiosError({ status: 500, message: "Request failed with status code 500" });
  expect(fetchErrorMessage(bare500)).toBe("Trenston is having trouble right now. Try again in a few seconds.");
  const bare400 = axiosError({ status: 400, message: "Request failed with status code 400" });
  expect(apiErrorMessage(bare400, "Could not save")).toBe("Could not save");
  expect(fetchErrorMessage(bare400)).toBe("Could not load data. Check your connection and try again.");
});

test("timeouts, expired sessions and rate limits get plain language", () => {
  expect(friendlyRequestError(axiosError({ code: "ECONNABORTED", message: "timeout of 20000ms exceeded" })))
    .toBe("Request timed out. The server may be busy. Try again.");
  expect(friendlyRequestError(axiosError({ status: 401 }))).toBe("Your session has expired. Sign in again to continue.");
  expect(friendlyRequestError(axiosError({ status: 429 }))).toBe("Too many requests. Wait a moment and try again.");
});

test("the Clerk token timeout is translated everywhere, not shown as a code", () => {
  const err = new Error("clerk-token-timeout");
  expect(apiErrorMessage(err)).toBe("Sign-in is still loading. Wait a moment and try again.");
  expect(fetchErrorMessage(err)).toBe("Sign-in is still loading. Wait a moment and try again.");
});

test("non-request errors keep their own message", () => {
  expect(apiErrorMessage(new Error("Choose at least one department."))).toBe("Choose at least one department.");
  expect(apiErrorMessage("Plain string message")).toBe("Plain string message");
  expect(friendlyRequestError(new Error("anything"))).toBeNull();
});

test("browser noise, cancels and stale chunks do not raise a toast", () => {
  expect(shouldReportGlobalError(null, "ResizeObserver loop completed with undelivered notifications.")).toBe(false);
  expect(shouldReportGlobalError(null, "Script error.")).toBe(false);
  expect(shouldReportGlobalError({ name: "CanceledError", message: "canceled" })).toBe(false);
  expect(shouldReportGlobalError({ name: "ChunkLoadError", message: "Loading chunk 9 failed." })).toBe(false);
  expect(shouldReportGlobalError(new TypeError("x is undefined"))).toBe(true);
});
