"use client";

import * as React from "react";
import { Command } from "cmdk";
import {
  Boxes,
  Bot,
  CircleDollarSign,
  Gauge,
  Inbox,
  KeyRound,
  LayoutDashboard,
  ListChecks,
  Network,
  Plug,
  Radio,
  Search,
  Settings,
  Users,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { Dialog, DialogContent, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

const navGroups = [
  {
    title: "Visão geral",
    items: [
      { label: "Dashboard", icon: LayoutDashboard, href: "/" },
      { label: "Projetos", icon: Boxes, href: "/projects" },
      { label: "Issues", icon: ListChecks, href: "/issues" },
      { label: "Minhas Issues", icon: ListChecks, href: "/my-issues" },
    ],
  },
  {
    title: "Construir",
    items: [
      { label: "Squad Builder", icon: Network, href: "/squad-builder" },
      { label: "Chat Console", icon: Bot, href: "/chat" },
      { label: "Agents", icon: Users, href: "/agents" },
    ],
  },
  {
    title: "Operar",
    items: [
      { label: "Live Panel", icon: Radio, href: "/live" },
      { label: "Seats", icon: KeyRound, href: "/seats" },
      { label: "Sessions", icon: Plug, href: "/sessions" },
      { label: "FinOps", icon: CircleDollarSign, href: "/finops" },
      { label: "Observability", icon: Gauge, href: "/observability" },
    ],
  },
  {
    title: "Workspace",
    items: [
      { label: "Inbox", icon: Inbox, href: "/inbox" },
      { label: "Settings", icon: Settings, href: "/settings" },
    ],
  },
];

export function CommandPalette({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const router = useRouter();

  React.useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        onOpenChange(true);
      }
    };

    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, [onOpenChange]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl p-0 overflow-hidden shadow-2xl" showClose={false}>
        <div className="sr-only">
          <DialogTitle>Command Palette</DialogTitle>
          <DialogDescription>Search through the workspace</DialogDescription>
        </div>
        <Command
          className="flex h-full w-full flex-col overflow-hidden bg-popover text-popover-foreground rounded-xl"
          label="Command Menu"
        >
          <div className="flex items-center border-b px-3 border-border">
            <Search className="mr-2 h-4 w-4 shrink-0 opacity-50" />
            <Command.Input
              className="flex h-11 w-full rounded-md bg-transparent py-3 text-sm outline-none placeholder:text-muted-foreground disabled:cursor-not-allowed disabled:opacity-50"
              placeholder="Digite um comando ou busque..."
            />
          </div>
          <Command.List className="max-h-[300px] overflow-y-auto overflow-x-hidden p-2">
            <Command.Empty className="py-6 text-center text-sm">
              Nenhum resultado encontrado.
            </Command.Empty>
            {navGroups.map((group) => (
              <Command.Group
                key={group.title}
                heading={<span className="text-xs font-semibold text-muted-foreground px-2 py-1 block">{group.title}</span>}
                className="overflow-hidden text-foreground [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:py-1.5 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:font-medium [&_[cmdk-group-heading]]:text-muted-foreground"
              >
                {group.items.map((item) => (
                  <Command.Item
                    key={item.href}
                    value={item.label}
                    onSelect={() => {
                      router.push(item.href);
                      onOpenChange(false);
                    }}
                    className={cn(
                      "relative flex cursor-default select-none items-center rounded-sm px-2 py-1.5 text-sm outline-none",
                      "aria-selected:bg-accent aria-selected:text-accent-foreground data-[disabled=true]:pointer-events-none data-[disabled=true]:opacity-50"
                    )}
                  >
                    <item.icon className="mr-2 h-4 w-4" />
                    <span>{item.label}</span>
                  </Command.Item>
                ))}
              </Command.Group>
            ))}
          </Command.List>
        </Command>
      </DialogContent>
    </Dialog>
  );
}
