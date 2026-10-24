import * as React from "react";
import { cn } from "@/lib/utils";

// Static by design: DESIGN.md only allows motion for state changes, so no pulse.
function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return <div data-slot="skeleton" aria-hidden className={cn("rounded-sm bg-sunken", className)} {...props} />;
}

export { Skeleton };
