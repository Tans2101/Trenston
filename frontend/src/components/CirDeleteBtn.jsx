import { Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Circular black trash button (Uiverse-style) for destructive row/detail actions.
 */
export default function CirDeleteBtn({
  onClick,
  disabled = false,
  className,
  title = "Delete",
  "aria-label": ariaLabel,
  "data-testid": testId,
  size = "sm",
  type = "button",
}) {
  return (
    <button
      type={type}
      onClick={(e) => {
        e.stopPropagation();
        onClick?.(e);
      }}
      disabled={disabled}
      title={title}
      aria-label={ariaLabel || title}
      data-testid={testId}
      className={cn("cir-delete", size === "md" && "cir-delete--md", className)}
    >
      <Trash2 strokeWidth={1.75} aria-hidden />
    </button>
  );
}
