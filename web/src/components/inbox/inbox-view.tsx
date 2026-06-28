"use client";

import { useState, useEffect, useCallback } from "react";
import { Inbox as InboxIcon, Archive, CheckCircle2, Circle, RefreshCcw } from "lucide-react";
import { EmptyState } from "@/components/ui/empty-state";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api-client";
import type { InboxEvent } from "@/lib/api-types";
import { cn } from "@/lib/utils";

export function InboxView({
  initialEvents,
  initialUnreadCount,
  initialError,
}: {
  initialEvents: InboxEvent[];
  initialUnreadCount: number;
  initialError: string | null;
}) {
  const [events, setEvents] = useState<InboxEvent[]>(initialEvents);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState("unread");
  const [unreadCount, setUnreadCount] = useState(initialUnreadCount);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(initialError);

  const fetchInbox = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await api.listInbox({
        archived: false,
        read: activeTab === "unread" ? false : activeTab === "read" ? true : undefined,
      });
      setEvents(data);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setLoading(false);
    }
  }, [activeTab]);

  const fetchUnreadCount = useCallback(async () => {
    try {
      const data = await api.unreadInboxCount();
      setUnreadCount(data.count);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  }, []);

  useEffect(() => {
    fetchInbox();
    fetchUnreadCount();
  }, [fetchInbox, fetchUnreadCount]);

  const handleMarkRead = async (eventId: string) => {
    try {
      setError(null);
      await api.markInboxRead(eventId);
      await fetchInbox();
      await fetchUnreadCount();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  };

  const handleBulkArchive = async () => {
    const ids = selectedIds.size > 0 ? Array.from(selectedIds) : events.map((e) => e.id);
    if (ids.length === 0) return;
    try {
      setError(null);
      await api.archiveInboxEvents(ids);
      setSelectedIds(new Set());
      await fetchInbox();
      await fetchUnreadCount();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  };

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  return (
    <div className="flex h-full flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Inbox</h1>
          <p className="text-sm text-muted-foreground">Gerencie seus eventos e notificações do workspace.</p>
        </div>
        <Button variant="outline" size="sm" className="gap-2" onClick={handleBulkArchive} disabled={loading || events.length === 0}>
          <Archive className="size-4" />
          Bulk Archive{selectedIds.size > 0 ? ` (${selectedIds.size})` : ""}
        </Button>
        <Button variant="ghost" size="sm" className="gap-2" onClick={fetchInbox} disabled={loading}>
          <RefreshCcw className={cn("size-4", loading && "animate-spin")} />
          Refresh
        </Button>
      </div>

      {error && (
        <div className="rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full" defaultValue="unread">
        <TabsList>
          <TabsTrigger value="unread" className="gap-2">
            <Circle className="size-3.5" />
            Unread
            <Badge variant="default" className="ml-1 h-5 px-1.5 text-[10px]">{unreadCount}</Badge>
          </TabsTrigger>
          <TabsTrigger value="read" className="gap-2">
            <CheckCircle2 className="size-3.5" />
            Read
          </TabsTrigger>
          <TabsTrigger value="all" className="gap-2">
            <InboxIcon className="size-3.5" />
            All Events
          </TabsTrigger>
        </TabsList>

        <div className="mt-6 rounded-xl border border-border bg-card p-6 shadow-sm min-h-[400px]">
          {loading ? (
            <div className="space-y-4 animate-pulse">
              <div className="h-16 rounded-lg bg-muted/50 w-full" />
              <div className="h-16 rounded-lg bg-muted/50 w-full" />
              <div className="h-16 rounded-lg bg-muted/50 w-full" />
            </div>
          ) : events.length === 0 ? (
            <TabsContent value={activeTab} className="mt-0 h-full">
              <EmptyState
                icon={InboxIcon}
                title="Sua caixa de entrada está vazia"
                description={`Não há eventos marcados como '${activeTab}' no momento.`}
              />
            </TabsContent>
          ) : (
            <TabsContent value={activeTab} className="mt-0 space-y-3">
              {events.map((event) => (
                <div
                  key={event.id}
                  className={cn(
                    "flex items-start gap-4 rounded-lg border p-4 transition-colors hover:bg-muted/50",
                    selectedIds.has(event.id)
                      ? "border-primary bg-primary/5"
                      : "border-border",
                    !event.read && "bg-accent/30",
                  )}
                >
                  <input
                    type="checkbox"
                    checked={selectedIds.has(event.id)}
                    onChange={() => toggleSelect(event.id)}
                    className="mt-1 h-4 w-4 rounded border-border"
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="inline-flex items-center rounded-md border border-border bg-muted px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                        {event.type.replace(/_/g, " ")}
                      </span>
                      {!event.read && (
                        <span className="h-2 w-2 rounded-full bg-accent animate-pulse" />
                      )}
                    </div>
                    <h3 className="text-sm font-medium leading-tight">{event.title}</h3>
                    {event.message && (
                      <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{event.message}</p>
                    )}
                    {event.created_at && (
                      <p className="text-[10px] text-muted-foreground/60 mt-1">
                        {new Date(event.created_at).toLocaleString()}
                      </p>
                    )}
                  </div>
                  {!event.read && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="shrink-0"
                      onClick={() => handleMarkRead(event.id)}
                    >
                      <CheckCircle2 className="size-4" />
                    </Button>
                  )}
                </div>
              ))}
            </TabsContent>
          )}
        </div>
      </Tabs>
    </div>
  );
}
