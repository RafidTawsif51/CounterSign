import * as React from "react";
import { fieldClass } from "@/components/ui/input";
import { cn } from "@/lib/utils";

function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(fieldClass, "field-sizing-content min-h-20 px-2.5 py-1.5", className)}
      {...props}
    />
  );
}

export { Textarea };
