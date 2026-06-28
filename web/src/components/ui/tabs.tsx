"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

type TabsContextValue = {
  value: string;
  setValue: (value: string) => void;
};

const TabsContext = React.createContext<TabsContextValue | null>(null);

function useTabs() {
  const context = React.useContext(TabsContext);
  if (!context) throw new Error("Tabs components must be used within Tabs");
  return context;
}

function Tabs({
  value,
  defaultValue,
  onValueChange,
  children,
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement> & {
  value?: string;
  defaultValue: string;
  onValueChange?: (value: string) => void;
}) {
  const [internalValue, setInternalValue] = React.useState(defaultValue);
  const currentValue = value ?? internalValue;
  const setValue = React.useCallback(
    (nextValue: string) => {
      setInternalValue(nextValue);
      onValueChange?.(nextValue);
    },
    [onValueChange],
  );

  return (
    <TabsContext.Provider value={{ value: currentValue, setValue }}>
      <div className={cn("space-y-4", className)} {...props}>
        {children}
      </div>
    </TabsContext.Provider>
  );
}

function TabsList({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      role="tablist"
      className={cn("inline-flex h-10 items-center rounded-md border border-border bg-muted p-1", className)}
      {...props}
    />
  );
}

function TabsTrigger({
  value,
  className,
  children,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { value: string }) {
  const tabs = useTabs();
  const active = tabs.value === value;
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      className={cn(
        "aop-focus inline-flex h-8 items-center justify-center rounded px-3 text-sm font-medium transition-all",
        active
          ? "bg-background text-foreground shadow-sm"
          : "text-muted-foreground hover:text-foreground",
        className,
      )}
      onClick={() => tabs.setValue(value)}
      {...props}
    >
      {children}
    </button>
  );
}

function TabsContent({
  value,
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement> & { value: string }) {
  const tabs = useTabs();
  if (tabs.value !== value) return null;
  return <div role="tabpanel" className={cn("aop-fade-in", className)} {...props} />;
}

export { Tabs, TabsList, TabsTrigger, TabsContent };
