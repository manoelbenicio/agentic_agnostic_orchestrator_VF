"use client";

import { useAgentTraceWs } from "@/lib/hooks";
import type { TraceEvent } from "@/lib/api-types";
import {
  Activity,
  AlertCircle,
  Brain,
  Clock,
  Radio,
  Zap,
} from "lucide-react";
import { useState } from "react";

const layerColors: Record<string, string> = {
  orchestration: "text-blue-400",
  execution: "text-emerald-400",
  tool_use: "text-amber-400",
  llm: "text-purple-400",
  system: "text-gray-400",
};

const signalIcons: Record<string, typeof Activity> = {
  start: Radio,
  progress: Activity,
  complete: Zap,
  error: AlertCircle,
  thought: Brain,
};

function TraceEventRow({ event }: { event: TraceEvent }) {
  const Icon = signalIcons[event.signal_type] ?? Activity;
  const layerColor = layerColors[event.layer] ?? "text-muted-foreground";

  return (
    <div className="group flex items-start gap-3 border-b border-border/50 px-4 py-3 transition-colors last:border-0 hover:bg-accent/30">
      <div className={`mt-0.5 ${layerColor}`}>
        <Icon className="size-4" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className={`text-xs font-semibold uppercase ${layerColor}`}>
            {event.layer}
          </span>
          <span className="text-[10px] text-muted-foreground">
            {event.signal_type}
          </span>
          {event.token_burn > 0 && (
            <span className="rounded-full bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-medium text-amber-400">
              🔥 {event.token_burn} tok
            </span>
          )}
        </div>
        <p className="mt-0.5 text-sm text-foreground">{event.message}</p>
        <div className="mt-1 flex items-center gap-3 text-[10px] text-muted-foreground">
          <span className="font-mono">{event.trace_id.slice(0, 8)}…</span>
          {event.runtime_id && (
            <span>rt:{event.runtime_id.slice(0, 8)}</span>
          )}
        </div>
      </div>
    </div>
  );
}

interface LiveTracePanelProps {
  agentId: string;
  agentLabel?: string;
}

export function LiveTracePanel({ agentId, agentLabel }: LiveTracePanelProps) {
  const { events, connected, error } = useAgentTraceWs(agentId);
  const [expanded, setExpanded] = useState(true);

  const totalBurn = events.reduce((sum, e) => sum + (e.token_burn || 0), 0);

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card shadow-sm">
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center justify-between border-b border-border bg-gradient-to-r from-card to-accent/10 px-4 py-3 text-left transition-colors hover:from-accent/10 hover:to-accent/20"
      >
        <div className="flex items-center gap-3">
          <div className="relative">
            <Brain className="size-5 text-primary" />
            {connected && (
              <span className="absolute -right-0.5 -top-0.5 size-2 animate-pulse rounded-full bg-success" />
            )}
          </div>
          <div>
            <div className="text-sm font-semibold text-foreground">
              {agentLabel || agentId}
            </div>
            <div className="text-[10px] text-muted-foreground">
              {connected ? "● LIVE" : error ? "● OFFLINE" : "● POLLING"}
              {" · "}
              {events.length} event{events.length !== 1 ? "s" : ""}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {totalBurn > 0 && (
            <div className="flex items-center gap-1 rounded-full bg-amber-500/10 px-2 py-1 text-xs text-amber-400">
              <Zap className="size-3" />
              {totalBurn} tok
            </div>
          )}
          <div
            className={`size-2 rounded-full ${
              connected
                ? "bg-success animate-pulse"
                : error
                  ? "bg-destructive"
                  : "bg-amber-400"
            }`}
          />
        </div>
      </button>

      {/* Stream */}
      {expanded && (
        <div className="max-h-96 overflow-y-auto">
          {events.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
              <Clock className="mb-2 size-8 opacity-40" />
              <p className="text-sm">Waiting for trace events…</p>
              <p className="text-xs opacity-60">
                Events stream in real-time via WebSocket
              </p>
            </div>
          ) : (
            events.map((event, i) => (
              <TraceEventRow key={`${event.event_id}-${i}`} event={event} />
            ))
          )}
        </div>
      )}
    </div>
  );
}
