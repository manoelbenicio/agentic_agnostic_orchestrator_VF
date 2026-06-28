import * as React from "react";
import type { ComponentType } from "react";

import { cn } from "@/lib/utils";

type EmptyStateProps = React.HTMLAttributes<HTMLDivElement> & {
  icon?: ComponentType<{ className?: string }>;
  title: string;
  description?: string;
  action?: React.ReactNode;
};

function EmptyState({
  className,
  icon: Icon,
  title,
  description,
  action,
  ...props
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "aop-card flex min-h-48 flex-col items-center justify-center gap-3 px-6 py-12 text-center",
        className,
      )}
      {...props}
    >
      {Icon && (
        <div className="flex size-12 items-center justify-center rounded-lg bg-muted text-muted-foreground">
          <Icon className="size-6" />
        </div>
      )}
      <div>
        <h3 className="text-sm font-semibold text-foreground">{title}</h3>
        {description && (
          <p className="mt-1 max-w-md text-sm leading-6 text-muted-foreground">
            {description}
          </p>
        )}
      </div>
      {action && <div className="pt-1">{action}</div>}
    </div>
  );
}

export { EmptyState };
