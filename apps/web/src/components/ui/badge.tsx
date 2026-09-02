import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

// Pills are for status only. `long` and `short` carry market meaning and must
// not be borrowed for decoration.
const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
  {
    variants: {
      variant: {
        default: "border-long/25 bg-long-soft text-long",
        long: "border-long/25 bg-long-soft text-long",
        short: "border-short/25 bg-short-soft text-short",
        secondary: "border-transparent bg-muted text-muted-foreground",
        destructive: "border-short/25 bg-short-soft text-short",
        outline: "border-border text-foreground",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  )
}

export { Badge, badgeVariants }
