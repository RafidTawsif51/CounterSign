import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "radix-ui";
import { cn } from "@/lib/utils";

// Variants per DESIGN.md: one primary per view; danger is for reject and block only.
const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-1.5 rounded-md border font-medium whitespace-nowrap transition-colors disabled:pointer-events-none disabled:opacity-45 [&_svg]:pointer-events-none [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        primary: "border-accent bg-accent text-accent-ink hover:border-accent-hover hover:bg-accent-hover",
        secondary: "border-rule-strong bg-surface text-ink hover:bg-sunken",
        ghost: "border-transparent bg-transparent text-ink-muted hover:bg-sunken hover:text-ink",
        danger: "border-blocked bg-surface text-blocked-ink hover:bg-blocked-tint",
        link: "h-auto border-transparent px-0 text-accent underline-offset-4 hover:underline",
      },
      size: {
        sm: "h-7 px-2.5 text-sm",
        md: "h-8 px-3 text-base",
        icon: "size-8 p-0",
        "icon-sm": "size-7 p-0",
      },
    },
    defaultVariants: { variant: "secondary", size: "md" },
  },
);

function Button({
  className,
  variant,
  size,
  asChild = false,
  type,
  ...props
}: React.ComponentProps<"button"> & VariantProps<typeof buttonVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot.Root : "button";
  return (
    <Comp
      data-slot="button"
      type={asChild ? undefined : (type ?? "button")}
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  );
}

export { Button, buttonVariants };
