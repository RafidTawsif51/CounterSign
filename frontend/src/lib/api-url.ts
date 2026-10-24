/** The FastAPI server, without a trailing slash. Empty means same origin. */
export const API_URL = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");
