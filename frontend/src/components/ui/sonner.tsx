import { CircleCheck, Info, Loader2, OctagonX, TriangleAlert } from "lucide-react";
import { Toaster as Sonner, type ToasterProps } from "sonner";
import { iconProps } from "@/components/shared/icon";
import { useTheme } from "@/hooks/use-theme";

// Toasts confirm actions in the same words as the button ("Payment rejected"). Quiet: neutral icons, because
// status colors mean payment state and a toast is about an action, not a payment.
function Toaster(props: ToasterProps) {
  const theme = useTheme();
  return (
    <Sonner
      theme={theme}
      position="bottom-right"
      duration={4000}
      offset={16}
      gap={8}
      icons={{
        success: <CircleCheck {...iconProps} className="text-ink-muted" />,
        info: <Info {...iconProps} className="text-ink-muted" />,
        warning: <TriangleAlert {...iconProps} className="text-ink" />,
        error: <OctagonX {...iconProps} className="text-ink" />,
        loading: <Loader2 {...iconProps} className="animate-spin text-ink-muted" />,
      }}
      toastOptions={{
        classNames: {
          toast: "!rounded-lg !border-rule !bg-surface !text-ink !shadow-overlay !font-sans !text-sm !gap-2.5 !px-3.5 !py-3",
          title: "!font-medium",
          icon: "!self-start !mt-px",
          description: "!text-sm !text-ink-muted",
          actionButton: "!rounded-md !bg-accent !text-accent-ink",
          cancelButton: "!rounded-md !bg-sunken !text-ink",
        },
      }}
      {...props}
    />
  );
}

export { Toaster };
