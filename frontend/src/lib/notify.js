/**
 * Safe toast helpers. Sonner crashes React (ErrorBoundary) when given a non-string
 * child — FastAPI often returns `detail` as a list or `{message, reason}` object.
 *
 * Importing this module patches `toast.error` on the shared sonner singleton so
 * every existing `import { toast } from "sonner"` call site is protected.
 */
import { toast } from "sonner";
import { apiErrorMessage } from "@/lib/api";

function coerceToastMessage(message, fallback = "Something went wrong") {
  if (typeof message === "string" || typeof message === "number" || typeof message === "boolean") {
    return String(message);
  }
  // Allow legitimate React nodes (sonner supports custom JSX titles).
  if (message != null && typeof message === "object" && message.$$typeof) {
    return message;
  }
  if (message == null) return fallback;
  return apiErrorMessage(message, fallback);
}

const _error = toast.error.bind(toast);
toast.error = (message, data) => _error(coerceToastMessage(message, "Something went wrong"), data);

/** Prefer this in catch blocks: always turns Axios / FastAPI errors into copy. */
export function toastError(errorOrMessage, fallback = "Something went wrong") {
  if (typeof errorOrMessage === "string") {
    toast.error(errorOrMessage);
    return;
  }
  toast.error(apiErrorMessage(errorOrMessage, fallback));
}

export { toast };
