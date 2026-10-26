// The landing-only build (VITE_LANDING_ONLY=true): the deployed site is just the project page, at /. Links into the app
// go to VITE_APP_URL when it is set and are left out when it is not, so the page never links to a screen that is not there.

export const LANDING_ONLY = import.meta.env.VITE_LANDING_ONLY === "true";

const APP_URL = (import.meta.env.VITE_APP_URL ?? "").trim().replace(/\/+$/, "");

/** True when the page can link into the app: the full build, or a landing build that knows where the app lives. */
export const HAS_APP = !LANDING_ONLY || APP_URL !== "";

/** Where a link to an app path points: the path itself in the full build, the app's own address in a landing build. */
export function appHref(path: string): string {
  return LANDING_ONLY ? APP_URL + path : path;
}
