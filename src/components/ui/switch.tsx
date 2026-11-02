import * as React from "react";
import { cn } from "@/lib/utils";

export interface SwitchProps extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, "role" | "aria-checked" | "onClick"> {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  id?: string;
  "aria-label"?: string;
}

/** A pencil-drawn switch whose knob is a small bulb: lit when on. */
const Switch = React.forwardRef<HTMLButtonElement, SwitchProps>(
  ({ className, checked, onCheckedChange, disabled, id, "aria-label": ariaLabel, ...props }, ref) => {
    return (
      <button
        type="button"
        role="switch"
        ref={ref}
        id={id}
        aria-label={ariaLabel}
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onCheckedChange(!checked)}
        className={cn("ui-switch", className)}
        {...props}
      >
        <span className="ui-switch-bulb" />
      </button>
    );
  },
);
Switch.displayName = "Switch";

export { Switch };
