"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

type DropdownContextValue = {
  open: boolean;
  setOpen: (open: boolean) => void;
};

const DropdownContext = React.createContext<DropdownContextValue | null>(null);

function useDropdown() {
  const context = React.useContext(DropdownContext);
  if (!context) throw new Error("Dropdown components must be used within Dropdown");
  return context;
}

function Dropdown({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = React.useState(false);
  return (
    <DropdownContext.Provider value={{ open, setOpen }}>
      <div className="relative inline-block">{children}</div>
    </DropdownContext.Provider>
  );
}

function DropdownTrigger({ className, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const { open, setOpen } = useDropdown();
  return (
    <button
      type="button"
      aria-haspopup="menu"
      aria-expanded={open}
      className={cn("aop-focus", className)}
      onClick={() => setOpen(!open)}
      {...props}
    />
  );
}

function DropdownContent({
  className,
  align = "end",
  ...props
}: React.HTMLAttributes<HTMLDivElement> & { align?: "start" | "end" }) {
  const { open, setOpen } = useDropdown();
  React.useEffect(() => {
    if (!open) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, setOpen]);

  if (!open) return null;
  return (
    <>
      <button
        type="button"
        aria-label="Close menu"
        className="fixed inset-0 z-40 cursor-default"
        onClick={() => setOpen(false)}
      />
      <div
        role="menu"
        className={cn(
          "aop-card aop-float-in absolute z-50 mt-2 min-w-48 overflow-hidden p-1 shadow-lg",
          align === "start" ? "left-0" : "right-0",
          className,
        )}
        {...props}
      />
    </>
  );
}

function DropdownItem({
  className,
  onClick,
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const { setOpen } = useDropdown();
  return (
    <button
      type="button"
      role="menuitem"
      className={cn(
        "aop-focus flex w-full items-center gap-2 rounded px-2.5 py-2 text-left text-sm transition-colors hover:bg-accent hover:text-accent-foreground",
        className,
      )}
      onClick={(event) => {
        onClick?.(event);
        setOpen(false);
      }}
      {...props}
    />
  );
}

function DropdownSeparator({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("-mx-1 my-1 h-px bg-border", className)} {...props} />;
}

export { Dropdown, DropdownTrigger, DropdownContent, DropdownItem, DropdownSeparator };
