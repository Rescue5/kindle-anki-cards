import * as React from "react";
import { cn } from "@/lib/utils";

/** A note written in the margin by hand, not a coloured pill. */
export function Badge({ className, ...props }: React.HTMLAttributes<HTMLSpanElement>) {
  return <span className={cn("ui-badge", className)} {...props} />;
}
