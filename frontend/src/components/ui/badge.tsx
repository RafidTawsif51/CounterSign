import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "radix-ui";
import { cn } from "@/lib/utils";

// Radius 4, never a pill. Status variants are for payment state only; use StatusBadge for those.
const badgeVariants = cva(
  "inline-flex h-5 w-fit shrink-0 items-center gap-1.5 rounded-sm border px-1.5 text-xs font-medium whitespace-nowrap transition-colors [&>svg]:size-3 [&>svg]:shrink-0",
  {
    variants: {
      variant: {
        neutral: "border-rule-strong bg-surface text-ink-muted",
        accent: "border-transparent bg-accent-tint text-accent",
        pending: "border-transparent bg-pending-tint text-pending-ink",
        paid: "border-transparent bg-paid-tint text-paid-ink",
        held: "border-transparent bg-held-tint text-held-ink",
        blocked: "border-transparent bg-blocked-tint text-blocked-ink",
      },
    },
    defaultVariants: { variant: "neutral" },
  },
);

function Badge({
  className,
  variant,
  asChild = false,
  ...props
}: React.ComponentProps<"span"> & VariantProps<typeof badgeVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot.Root : "span";
  return <Comp data-slot="badge" className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
