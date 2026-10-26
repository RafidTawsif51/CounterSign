// A link from the project page into the app. In the full build it is a router link (or a plain one for a new tab); in the
// landing-only build it is a plain link to VITE_APP_URL. Render it only when HAS_APP (lib/landing.ts).

import type { AnchorHTMLAttributes } from "react";
import { Link } from "react-router-dom";
import { appHref, LANDING_ONLY } from "@/lib/landing";

type Props = { to: string; newTab?: boolean } & Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href">;

export function AppLink({ to, newTab, ...rest }: Props) {
  const tab = newTab ? { target: "_blank", rel: "noreferrer" } : {};
  if (LANDING_ONLY || newTab) return <a href={appHref(to)} {...tab} {...rest} />;
  return <Link to={to} {...rest} />;
}
