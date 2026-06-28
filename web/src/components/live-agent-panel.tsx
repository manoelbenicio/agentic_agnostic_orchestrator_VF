"use client";

import { Radio, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { api, traceAgentWebSocketUrl } from "@/lib/api-client";
import type { Agent, TraceEvent } from "@/lib/api-types";

export function LiveAgentPanel() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [selectedAgent, setSelectedAgent] = useState("");
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [state, setState] = useState<"loading" | "connected" | "fallback" | "empty" | "error">("loading");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    api
      .listAgents()
      .then((items) => {
        if (!active) return;
        setAgents(items);
        setSelectedAgent(items[0]?.agent_id || "agent-a");
        setState(items.length ? "loading" : "empty");
      })
      .catch((err) => {
        if (!active) return;
        setError(err instanceof Error ? err.message : "Unable to list agents");
        setSelectedAgent("agent-a");
        setState("fallback");
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!selectedAgent) return;
    let active = true;
    let socket: WebSocket | null = null;

    async function loadTrace() {
      try {
        const trace = await api.traceAgent(selectedAgent);
        if (active) {
          setEvents(trace);
          setState((current) => (current === "connected" ? current : "fallback"));
          setError(null);
        }
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : "Unable to load trace");
          setState("error");
        }
      }
    }

    try {
      socket = new WebSocket(traceAgentWebSocketUrl(selectedAgent));
      socket.onopen = () => {
        if (active) setState("connected");
      };
      socket.onmessage = (message) => {
        try {
          const event = JSON.parse(message.data) as TraceEvent;
          if (active) setEvents((current) => [event, ...current].slice(0, 20));
        } catch {
          return;
        }
      };
      socket.onerror = () => {
        if (active) void loadTrace();
      };
      socket.onclose = () => {
        if (active) void loadTrace();
      };
    } catch {
      void loadTrace();
    }

    const interval = window.setInterval(loadTrace, 8000);
    void loadTrace();
    return () => {
      active = false;
      window.clearInterval(interval);
      socket?.close();
    };
  }, [selectedAgent]);

  const totals = useMemo(
    () =>
      events.reduce(
        (acc, event) => ({
          tokens: acc.tokens + (event.token_burn || 0),
          seatSeconds: acc.seatSeconds + (event.seat_seconds || 0),
        }),
        { tokens: 0, seatSeconds: 0 },
      ),
    [events],
  );

  return (
    <section className="rounded-lg border border-border bg-card p-5 shadow-sm">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-sm font-semibold">Live Agent Panel</h2>
          <p className="mt-1 text-sm text-muted-foreground">Trace stream by agent/runtime.</p>
        </div>
        <div className="flex items-center gap-2">
          <select
            value={selectedAgent}
            onChange={(event) => setSelectedAgent(event.target.value)}
            className="h-9 rounded-md border border-input bg-background px-3 text-sm"
          >
            {agents.length ? (
              agents.map((agent) => (
                <option key={agent.agent_id} value={agent.agent_id}>
                  {agent.label}
                </option>
              ))
            ) : (
              <option value="agent-a">agent-a</option>
            )}
          </select>
          <span className="inline-flex h-9 items-center gap-2 rounded-md border border-border px-3 text-xs text-muted-foreground">
            {state === "connected" ? <Radio className="size-3.5 text-success" /> : <RefreshCw className="size-3.5" />}
            {state}
          </span>
        </div>
      </div>

      {error ? <div className="mt-3 text-sm text-destructive">{error}</div> : null}

      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <Metric label="Events" value={events.length.toString()} />
        <Metric label="Token burn" value={totals.tokens.toString()} />
        <Metric label="Seat seconds" value={totals.seatSeconds.toString()} />
      </div>

      <div className="mt-4 max-h-72 overflow-auto rounded-md border border-border">
        {events.length ? (
          events.map((event) => (
            <div key={event.event_id} className="border-b border-border p-3 last:border-b-0">
              <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <span>{event.runtime_id}</span>
                <span>{event.layer}</span>
                <span>{event.signal_type}</span>
              </div>
              <div className="mt-1 text-sm">{event.message}</div>
            </div>
          ))
        ) : (
          <div className="p-4 text-sm text-muted-foreground">No trace events yet.</div>
        )}
      </div>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-border bg-background p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 text-lg font-semibold">{value}</div>
    </div>
  );
}

