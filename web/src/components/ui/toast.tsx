"use client";

import * as React from "react";
import { CheckCircle2, Info, TriangleAlert, X, XCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type ToastVariant = "default" | "success" | "warning" | "destructive";
type Toast = {
  id: string;
  title: string;
  description?: string;
  variant?: ToastVariant;
};

type ToastContextValue = {
  toasts: Toast[];
  toast: (toast: Omit<Toast, "id">) => void;
  dismiss: (id: string) => void;
};

const ToastContext = React.createContext<ToastContextValue | null>(null);

const icons = {
  default: Info,
  success: CheckCircle2,
  warning: TriangleAlert,
  destructive: XCircle,
};

const iconClass = {
  default: "text-primary",
  success: "text-success",
  warning: "text-warning",
  destructive: "text-destructive",
};

function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = React.useState<Toast[]>([]);
  const dismiss = React.useCallback((id: string) => {
    setToasts((items) => items.filter((item) => item.id !== id));
  }, []);
  const toast = React.useCallback((nextToast: Omit<Toast, "id">) => {
    const id = crypto.randomUUID();
    setToasts((items) => [{ id, ...nextToast }, ...items].slice(0, 4));
    window.setTimeout(() => dismiss(id), 5000);
  }, [dismiss]);

  return (
    <ToastContext.Provider value={{ toasts, toast, dismiss }}>
      {children}
      <ToastViewport />
    </ToastContext.Provider>
  );
}

function useToast() {
  const context = React.useContext(ToastContext);
  if (!context) throw new Error("useToast must be used within ToastProvider");
  return context;
}

function ToastViewport() {
  const { toasts, dismiss } = useToast();
  return (
    <div className="fixed bottom-4 right-4 z-50 flex w-[min(24rem,calc(100vw-2rem))] flex-col gap-2">
      {toasts.map((item) => {
        const variant = item.variant ?? "default";
        const Icon = icons[variant];
        return (
          <div key={item.id} className="aop-card aop-float-in flex gap-3 p-3 shadow-lg">
            <Icon className={cn("mt-0.5 size-4 shrink-0", iconClass[variant])} />
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold">{item.title}</div>
              {item.description && (
                <div className="mt-0.5 text-sm leading-5 text-muted-foreground">
                  {item.description}
                </div>
              )}
            </div>
            <Button
              type="button"
              size="icon"
              variant="ghost"
              className="size-7"
              aria-label="Dismiss notification"
              onClick={() => dismiss(item.id)}
            >
              <X className="size-3.5" />
            </Button>
          </div>
        );
      })}
    </div>
  );
}

export { ToastProvider, ToastViewport, useToast };
