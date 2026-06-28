"use client";

import {
  Boxes,
  Bot,
  ChevronsUpDown,
  CircleDollarSign,
  Gauge,
  Inbox,
  KeyRound,
  LayoutDashboard,
  ListChecks,
  Menu,
  Network,
  PanelLeftClose,
  PanelLeftOpen,
  Plug,
  Radio,
  Search,
  Settings,
  Users,
  X,
} from "lucide-react";
import type { ComponentType, ReactNode } from "react";
import { useEffect, useMemo, useState } from "react";
import { usePathname } from "next/navigation";
import Link from "next/link";

import { HealthBadge } from "@/components/dashboard/HealthBadge";
import { ThemeToggle } from "@/components/theme-toggle";
import { Avatar } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Dropdown,
  DropdownContent,
  DropdownItem,
  DropdownSeparator,
  DropdownTrigger,
} from "@/components/ui/dropdown";
import { Input } from "@/components/ui/input";
import { Tooltip } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

type NavItem = {
  label: string;
  icon: ComponentType<{ className?: string }>;
  href: string;
  badge?: string;
  pulse?: boolean;
};

const navGroups: { title: string; items: NavItem[] }[] = [
  {
    title: "Visão geral",
    items: [
      { label: "Dashboard", icon: LayoutDashboard, href: "/" },
      { label: "Projetos", icon: Boxes, href: "/projects" },
      { label: "Issues", icon: ListChecks, href: "/issues" },
    ],
  },
  {
    title: "Construir",
    items: [
      { label: "Squad Builder", icon: Network, href: "/squad-builder" },
      { label: "Chat Console", icon: Bot, href: "/chat", badge: "AI" },
    ],
  },
  {
    title: "Operar",
    items: [
      { label: "Live Panel", icon: Radio, href: "/live", pulse: true },
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
      { label: "My Issues", icon: Users, href: "/my-issues" },
      { label: "Settings", icon: Settings, href: "/settings" },
    ],
  },
];

function isActive(pathname: string, href: string) {
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}

function SidebarContent({
  collapsed,
  pathname,
  onNavigate,
}: {
  collapsed: boolean;
  pathname: string;
  onNavigate?: () => void;
}) {
  return (
    <>
      <div className="flex h-16 items-center gap-3 border-b border-sidebar-border px-3">
        <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm">
          <Gauge className="size-5" />
        </div>
        {!collapsed && (
          <div className="min-w-0 aop-wipe-in">
            <div className="truncate text-sm font-semibold leading-tight">AOP Control</div>
            <div className="truncate text-xs text-muted-foreground">
              Local-first runtime
            </div>
          </div>
        )}
      </div>

      <div className="px-3 pt-3">
        <Dropdown>
          <DropdownTrigger
            className={cn(
              "flex w-full items-center gap-2 rounded-lg border border-sidebar-border bg-card px-3 py-2 text-left text-sm shadow-sm transition-all hover:-translate-y-px hover:bg-sidebar-accent",
              collapsed && "justify-center px-2",
            )}
            aria-label="Workspace"
          >
            <span className="flex size-6 shrink-0 items-center justify-center rounded bg-primary/15 text-xs font-bold text-primary">
              A
            </span>
            {!collapsed && (
              <>
                <span className="min-w-0 flex-1 truncate font-medium">AOP Workspace</span>
                <ChevronsUpDown className="size-3.5 text-muted-foreground" />
              </>
            )}
          </DropdownTrigger>
          <DropdownContent align="start" className="w-56">
            <DropdownItem>
              <Gauge className="size-4" />
              AOP Workspace
              <Badge variant="success" className="ml-auto">
                Ativo
              </Badge>
            </DropdownItem>
            <DropdownSeparator />
            <DropdownItem>
              <Settings className="size-4" />
              Configurar workspace
            </DropdownItem>
          </DropdownContent>
        </Dropdown>
      </div>

      <nav className="flex-1 space-y-5 overflow-y-auto px-3 py-4">
        {navGroups.map((group) => (
          <div key={group.title} className="space-y-1">
            {!collapsed && (
              <div className="px-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {group.title}
              </div>
            )}
            {group.items.map((item) => {
              const Icon = item.icon;
              const active = isActive(pathname, item.href);
              const link = (
                <Link
                  key={item.label}
                  href={item.href}
                  onClick={onNavigate}
                  aria-current={active ? "page" : undefined}
                  className={cn(
                    "group relative flex h-10 items-center gap-3 rounded-lg text-sm transition-all hover:-translate-y-px",
                    collapsed ? "justify-center px-2" : "px-3",
                    active
                      ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground shadow-sm"
                      : "text-muted-foreground hover:bg-sidebar-accent/70 hover:text-sidebar-accent-foreground",
                  )}
                >
                  {active && (
                    <span className="absolute left-0 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r-full bg-accent" />
                  )}
                  <Icon className="size-4 shrink-0" />
                  {!collapsed && <span className="truncate">{item.label}</span>}
                  {!collapsed && item.pulse && (
                    <span className="ml-auto size-2 rounded-full bg-success ring-4 ring-success/20" />
                  )}
                  {!collapsed && item.badge && (
                    <span className="ml-auto rounded-full bg-primary/15 px-1.5 text-xs font-semibold text-primary">
                      {item.badge}
                    </span>
                  )}
                </Link>
              );
              return collapsed ? (
                <Tooltip key={item.label} label={item.label}>
                  {link}
                </Tooltip>
              ) : (
                link
              );
            })}
          </div>
        ))}
      </nav>

      <div className="border-t border-sidebar-border p-3">
        <div
          className={cn(
            "flex items-center gap-3 rounded-lg px-2 py-1.5",
            collapsed && "justify-center px-0",
          )}
        >
          <Avatar name="AOP" className="size-8" />
          {!collapsed && (
            <div className="min-w-0 flex-1 aop-wipe-in">
              <div className="truncate text-sm font-medium">AOP Runtime</div>
              <div className="truncate text-xs text-muted-foreground">Sistema local</div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

  const searchItems = useMemo(
    () =>
      navGroups.flatMap((group) =>
        group.items.map((item) => ({
          ...item,
          group: group.title,
        })),
      ),
    [],
  );

  const filteredSearchItems = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    if (!query) return searchItems;
    return searchItems.filter((item) =>
      `${item.label} ${item.group}`.toLowerCase().includes(query),
    );
  }, [searchItems, searchQuery]);

  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setSearchOpen(true);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  return (
    <div className="min-h-screen bg-background text-foreground">
      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <button
            type="button"
            aria-label="Close navigation"
            className="absolute inset-0 bg-background/80 backdrop-blur-sm"
            onClick={() => setMobileOpen(false)}
          />
          <aside className="aop-float-in relative flex h-full w-[min(19rem,calc(100vw-2rem))] flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground shadow-lg">
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label="Close navigation"
              className="absolute right-3 top-3 z-10"
              onClick={() => setMobileOpen(false)}
            >
              <X />
            </Button>
            <SidebarContent collapsed={false} pathname={pathname} />
          </aside>
        </div>
      )}

      <div
        className={cn(
          "grid min-h-screen transition-[grid-template-columns] duration-300 lg:grid",
          collapsed
            ? "lg:grid-cols-[76px_minmax(0,1fr)]"
            : "lg:grid-cols-[272px_minmax(0,1fr)]",
        )}
      >
        <aside className="hidden flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground lg:flex">
          <SidebarContent collapsed={collapsed} pathname={pathname} />
        </aside>

        <div className="flex min-w-0 flex-col">
          <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-border bg-background/85 px-4 backdrop-blur-md md:px-6">
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label="Open navigation"
              className="lg:hidden"
              onClick={() => setMobileOpen(true)}
            >
              <Menu />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
              className="hidden lg:inline-flex"
              onClick={() => setCollapsed((value) => !value)}
            >
              {collapsed ? <PanelLeftOpen /> : <PanelLeftClose />}
            </Button>

            <div className="hidden min-w-0 xl:block">
              <div className="text-sm font-semibold leading-tight">
                Agnostic Orchestration Platform
              </div>
              <div className="text-xs text-muted-foreground">
                HerdMaster + Herdr runtime foundation
              </div>
            </div>

            <Button
              id="aop-shell-search"
              type="button"
              variant="outline"
              className="mx-auto h-10 w-full max-w-xl justify-start gap-2 bg-card px-3 text-left text-sm font-normal text-muted-foreground shadow-sm"
              aria-label="Buscar no workspace"
              onClick={() => setSearchOpen(true)}
            >
              <Search className="size-4 shrink-0" />
              <span className="min-w-0 flex-1 truncate">Buscar no workspace</span>
              <kbd className="hidden rounded border border-border bg-muted px-1.5 py-0.5 font-mono text-xs sm:inline-flex">
                Ctrl K
              </kbd>
            </Button>

            <div className="flex shrink-0 items-center gap-2">
              <div className="hidden sm:block">
                <HealthBadge />
              </div>
              <ThemeToggle />
              <Avatar name="AOP" className="hidden size-9 md:flex" />
            </div>
          </header>

          <main className="mx-auto w-full max-w-[1440px] flex-1 px-4 py-5 md:px-8 md:py-8">
            <div className="aop-fade-in">{children}</div>
          </main>
        </div>
      </div>

      <Dialog open={searchOpen} onOpenChange={setSearchOpen}>
        <DialogContent className="max-w-2xl p-0" showClose={false}>
          <DialogHeader className="border-b border-border px-4 py-4">
            <DialogTitle className="flex items-center gap-2 text-base">
              <Search className="size-4 text-muted-foreground" />
              Busca do workspace
            </DialogTitle>
            <DialogDescription>
              Encontre projetos, agentes, issues e áreas operacionais.
            </DialogDescription>
          </DialogHeader>
          <div className="p-4">
            <Input
              autoFocus
              placeholder="Digite para buscar..."
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
            />
            <div className="mt-4 grid gap-2">
              {filteredSearchItems.map((item) => {
                const Icon = item.icon;
                return (
                  <Link
                    key={`${item.group}-${item.href}`}
                    href={item.href}
                    onClick={() => {
                      setSearchOpen(false);
                      setSearchQuery("");
                    }}
                    className="aop-focus flex items-center gap-3 rounded-lg border border-border bg-card px-3 py-2 text-sm transition-all hover:-translate-y-px hover:bg-accent hover:text-accent-foreground"
                  >
                    <Icon className="size-4 shrink-0" />
                    <span className="min-w-0 flex-1 truncate">{item.label}</span>
                    <span className="text-xs text-muted-foreground">{item.group}</span>
                  </Link>
                );
              })}
              {filteredSearchItems.length === 0 && (
                <div className="rounded-lg border border-border bg-muted px-3 py-6 text-center text-sm text-muted-foreground">
                  Nenhuma rota encontrada
                </div>
              )}
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
