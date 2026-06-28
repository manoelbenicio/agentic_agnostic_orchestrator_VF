"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import * as React from "react";

import { Button } from "@/components/ui/button";

const modes = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "System", icon: Monitor },
];

export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = React.useState(false);

  React.useEffect(() => setMounted(true), []);

  return (
    <div className="grid grid-cols-3 rounded-md border border-border bg-muted p-1">
      {modes.map((mode) => {
        const Icon = mode.icon;
        const active = mounted && theme === mode.value;
        return (
          <Button
            key={mode.value}
            type="button"
            variant={active ? "default" : "ghost"}
            size="icon"
            aria-label={`Use ${mode.label} theme`}
            title={mode.label}
            onClick={() => setTheme(mode.value)}
            className="h-8 w-8"
          >
            <Icon />
          </Button>
        );
      })}
    </div>
  );
}
