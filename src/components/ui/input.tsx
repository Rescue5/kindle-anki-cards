import * as React from "react";
import { cn } from "@/lib/utils";
import { PencilRule } from "@/components/sketch/sketch";

/** A text field written on a pencil line; the line warms to the lamp colour on focus. */
const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type, ...props }, ref) => (
    <span className="ui-field">
      <input type={type} className={cn("ui-input", className)} ref={ref} {...props} />
      <PencilRule className="ui-field-line" />
    </span>
  ),
);
Input.displayName = "Input";

export { Input };
