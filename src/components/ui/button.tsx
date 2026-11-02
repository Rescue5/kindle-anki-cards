import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";
import { PencilFrame } from "@/components/sketch/sketch";

// Night reading buttons: `default` is lit by the lamp, `secondary` is drawn in pencil.
const buttonVariants = cva("ui-button", {
  variants: {
    variant: {
      default: "ui-button-lit",
      secondary: "ui-button-drawn",
      ghost: "ui-button-ghost",
      destructive: "ui-button-drawn ui-button-danger",
    },
    size: {
      default: "h-10 px-4 text-[14.5px]",
      sm: "h-9 px-3 text-[13.5px]",
      lg: "h-11 px-5 text-[15.5px]",
      icon: "h-10 w-10 px-0",
    },
  },
  defaultVariants: {
    variant: "default",
    size: "default",
  },
});

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, children, ...props }, ref) => {
    if (asChild) return <Slot className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props}>{children}</Slot>;
    const drawn = variant === "secondary" || variant === "destructive";
    return (
      <button className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props}>
        {drawn ? <PencilFrame /> : null}
        {children}
      </button>
    );
  },
);
Button.displayName = "Button";

export { Button, buttonVariants };
