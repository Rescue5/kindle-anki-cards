import * as React from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { PencilRule } from "@/components/sketch/sketch";

/** A native select on a pencil line with a drawn chevron. */
export function Select({
  className,
  ...props
}: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <span className="ui-field ui-select-field">
      <select className={cn("ui-select", className)} {...props} />
      <ChevronDown className="ui-select-chevron" size={15} strokeWidth={1.7} aria-hidden="true" />
      <PencilRule variant={1} className="ui-field-line" />
    </span>
  );
}
