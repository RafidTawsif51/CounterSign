/**
 * A failed API call. `message` is a plain sentence a person can act on, never JSON or a stack trace; `status` is 0 when
 * the server could not be reached at all. The method and path stay on the error for logs and tests.
 */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly path: string,
    message: string,
    /** The server's own message (detail or detail.error), without the method and path. */
    readonly detail: string = message,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/**
 * FastAPI error bodies come as `{detail: "text"}`, `{detail: {error: "text", ...}}` (409s from review.py and run.py), or
 * `{detail: [{loc, msg}, ...]}` (422 validation). Turn any of them into one sentence.
 */
export function detailText(data: unknown): string | null {
  const detail = typeof data === "object" && data !== null && "detail" in data ? (data as { detail: unknown }).detail : null;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const parts = detail
      .map((d) => {
        if (typeof d !== "object" || d === null) return null;
        const { loc, msg } = d as { loc?: unknown; msg?: unknown };
        const field = Array.isArray(loc) ? loc.filter((x) => x !== "body").join(".") : "";
        return typeof msg === "string" ? (field ? `${field}: ${msg}` : msg) : null;
      })
      .filter(Boolean);
    return parts.length ? parts.join("; ") : null;
  }
  if (typeof detail === "object" && detail !== null && "error" in detail && typeof (detail as { error: unknown }).error === "string")
    return (detail as { error: string }).error;
  return null;
}

/** What to show for a status with no readable detail. */
export function statusText(status: number): string {
  if (status === 0) return "Can't reach the Countersign server";
  if (status === 404) return "Not found";
  if (status === 409) return "That conflicts with something already in progress";
  if (status === 422) return "The server did not accept that input";
  if (status === 429) return "Too many requests; wait a moment";
  if (status >= 500) return `The server had a problem (${status})`;
  return `The request failed (${status})`;
}

/** A sentence for any thrown value, for inline error states and toasts. */
export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error && err.message) return err.message;
  return "Something went wrong";
}
