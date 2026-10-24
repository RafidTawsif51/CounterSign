import { CircleCheck, Info, Loader2, OctagonX, TriangleAlert } from "lucide-react";
import { Toaster as Sonner, type ToasterProps } from "sonner";
import { iconProps } from "@/components/shared/icon";
import { useTheme } from "@/hooks/use-theme";

// Toasts confirm actions in the same words as the button ("Payment rejected").
function Toaster(props: ToasterProps) {
  const theme = useTheme();
  return (
    <Sonner
      theme={theme}
      position="bottom-right"
      icons={{
        success: <CircleCheck {...iconProps} className="text-paid-ink" />,
        info: <Info {...iconProps} className="text-accent" />,
        warning: <TriangleAlert {...iconProps} className="text-held-ink" />,
        error: <OctagonX {...iconProps} className="text-blocked-ink" />,
        loading: <Loader2 {...iconProps} className="animate-spin text-ink-muted" />,
      }}
      toastOptions={{
        classNames: {
          toast: "!rounded-lg !border-rule !bg-surface !text-ink !shadow-overlay !font-sans !text-base !gap-2",
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
