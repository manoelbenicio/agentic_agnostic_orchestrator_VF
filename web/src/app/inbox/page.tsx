import { InboxView } from "@/components/inbox/inbox-view";
import type { InboxEvent } from "@/lib/api-types";

const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8090";

async function loadInbox(): Promise<{
  events: InboxEvent[];
  unreadCount: number;
  error: string | null;
}> {
  try {
    const [eventsResponse, unreadResponse] = await Promise.all([
      fetch(`${apiBase}/inbox?archived=false&read=false`, {
        cache: "no-store",
        headers: { Accept: "application/json" },
      }),
      fetch(`${apiBase}/inbox/unread-count`, {
        cache: "no-store",
        headers: { Accept: "application/json" },
      }),
    ]);

    if (!eventsResponse.ok) {
      return {
        events: [],
        unreadCount: 0,
        error: `GET /inbox returned ${eventsResponse.status}`,
      };
    }
    if (!unreadResponse.ok) {
      return {
        events: (await eventsResponse.json()) as InboxEvent[],
        unreadCount: 0,
        error: `GET /inbox/unread-count returned ${unreadResponse.status}`,
      };
    }

    const unread = (await unreadResponse.json()) as { count: number };
    return {
      events: (await eventsResponse.json()) as InboxEvent[],
      unreadCount: unread.count,
      error: null,
    };
  } catch (cause) {
    return {
      events: [],
      unreadCount: 0,
      error: cause instanceof Error ? cause.message : String(cause),
    };
  }
}

export default async function InboxPage() {
  const { events, unreadCount, error } = await loadInbox();
  return <InboxView initialEvents={events} initialUnreadCount={unreadCount} initialError={error} />;
}
