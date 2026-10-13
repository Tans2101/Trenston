import { Info } from "lucide-react";
import * as PopoverPrimitive from "@radix-ui/react-popover";
import { GLOSSARY } from "@/lib/glossary";
import { cn } from "@/lib/utils";
import { shellRoot } from "@/components/guide/TourOverlay";

/**
 * A label with a small (i) that explains the term in plain words.
 * Tap on phones, click or keyboard on desktop.
 */
export default function Term({ id, children, className }) {
  const meaning = GLOSSARY[id];
  if (!meaning) return <span className={className}>{children}</span>;
  return (
    <span className={cn("inline-flex items-center gap-1", className)}>
      {children}
      <PopoverPrimitive.Root>
        <PopoverPrimitive.Trigger
          type="button"
          aria-label={`What does ${typeof children === "string" ? children : "this"} mean?`}
          data-testid={`term-${id}`}
          className="inline-flex h-4 w-4 items-center justify-center rounded-full text-helm-muted/70 transition-colors hover:text-helm-gold focus-visible:text-helm-gold focus-visible:outline-none"
        >
          <Info className="h-3.5 w-3.5" />
        </PopoverPrimitive.Trigger>
        <PopoverPrimitive.Portal container={shellRoot()}>
          <PopoverPrimitive.Content
            side="top"
            sideOffset={6}
            collisionPadding={12}
            className="z-[60] w-64 rounded-lg border border-helm-line bg-helm-card p-3 text-left font-sans text-sm normal-case leading-relaxed tracking-normal text-helm-fg shadow-xl outline-none"
          >
            {meaning}
          </PopoverPrimitive.Content>
        </PopoverPrimitive.Portal>
      </PopoverPrimitive.Root>
    </span>
  );
}
