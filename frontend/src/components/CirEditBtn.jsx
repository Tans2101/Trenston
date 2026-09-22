import { Pencil } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Circular edit button matching CirDeleteBtn (same shape/size treatment, pencil icon).
 */
export default function CirEditBtn({
  onClick,
  disabled = false,
  className,
  title = "Edit",
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
      <Pencil strokeWidth={1.75} aria-hidden />
    </button>
  );
}
