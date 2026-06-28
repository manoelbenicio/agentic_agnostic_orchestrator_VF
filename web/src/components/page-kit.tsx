"use client";

import type { ComponentType, ReactNode } from "react";

import { EmptyState as UiEmptyState } from "@/components/ui/empty-state";
import { cn } from "@/lib/utils";

export function PageHeader({
  title,
  description,
  icon: Icon,
  actions,
  eyebrow,
}: {
  title: string;
  description?: string;
  icon?: ComponentType<{ className?: string }>;
  actions?: ReactNode;
  eyebrow?: string;
}) {
  return (
    <header className="aop-float-in flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="flex min-w-0 items-start gap-3">
        {Icon && (
          <div className="mt-0.5 flex size-10 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground shadow-sm">
            <Icon className="size-5" />
          </div>
        )}
        <div className="min-w-0">
          {eyebrow && (
            <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              {eyebrow}
            </div>
          )}
          <h1 className="truncate text-2xl font-semibold tracking-normal text-foreground">
            {title}
          </h1>
          {description && (
            <p className="mt-1 max-w-3xl text-sm leading-6 text-muted-foreground">
              {description}
            </p>
          )}
        </div>
      </div>
      {actions && (
        <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>
      )}
    </header>
  );
}

export function PageSection({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return <section className={cn("aop-fade-in space-y-4", className)}>{children}</section>;
}

export function EmptyState({
  title,
  description,
  icon,
  action,
  className,
}: {
  title: string;
  description?: string;
  icon?: ComponentType<{ className?: string }>;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <UiEmptyState
      className={className}
      icon={icon}
      title={title}
      description={description}
      action={action}
    />
  );
}

export function ComingSoon({
  title,
  description,
  icon,
  note,
}: {
  title: string;
  description: string;
  icon: ComponentType<{ className?: string }>;
  note?: string;
}) {
  return (
    <div className="space-y-6">
      <PageHeader title={title} description={description} icon={icon} />
      <EmptyState
        title="Nenhum dado disponível"
        description={
          note ??
          "Esta área aguarda a API correspondente. Quando houver dados reais, eles serão exibidos aqui."
        }
        icon={icon}
      />
    </div>
  );
}
