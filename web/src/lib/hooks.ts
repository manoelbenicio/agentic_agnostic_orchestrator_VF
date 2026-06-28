'use client';

// ---------------------------------------------------------------------------
// AOP Control-Plane – React Hooks (useState / useEffect, zero external deps)
// ---------------------------------------------------------------------------

import { useState, useEffect, useCallback, useRef } from 'react';
import { api } from './api-client';
import type {
  HealthResponse,
  Agent,
  Seat,
  ProjectRollup,
  TraceEvent,
  TopologyGetResponse,
} from './api-types';

// ---------------------------------------------------------------------------
// Generic fetcher helper
// ---------------------------------------------------------------------------

interface UseFetchResult<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
}

function useFetch<T>(fetcher: () => Promise<T>, deps: unknown[] = []): UseFetchResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [trigger, setTrigger] = useState(0);

  const refetch = useCallback(() => {
    setTrigger((prev) => prev + 1);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    fetcher()
      .then((result) => {
        if (!cancelled) {
          setData(result);
          setLoading(false);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [trigger, ...deps]);

  return { data, loading, error, refetch };
}

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------

export function useHealth(): {
  data: HealthResponse | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
} {
  return useFetch(() => api.health());
}

// ---------------------------------------------------------------------------
// Agents
// ---------------------------------------------------------------------------

export function useAgents(): {
  agents: Agent[];
  loading: boolean;
  error: string | null;
  refetch: () => void;
} {
  const { data, loading, error, refetch } = useFetch(() => api.listAgents());
  return { agents: data ?? [], loading, error, refetch };
}

// ---------------------------------------------------------------------------
// Seats
// ---------------------------------------------------------------------------

export function useSeats(): {
  seats: Seat[];
  loading: boolean;
  error: string | null;
  refetch: () => void;
} {
  const { data, loading, error, refetch } = useFetch(() => api.getSeats());
  return { seats: data?.seats ?? [], loading, error, refetch };
}

// ---------------------------------------------------------------------------
// FinOps – Project Rollup
// ---------------------------------------------------------------------------

export function useProjectRollup(
  tenantId: string,
  projectId: string,
): {
  rollup: ProjectRollup | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
} {
  const { data, loading, error, refetch } = useFetch(
    () => api.projectRollup(tenantId, projectId),
    [tenantId, projectId],
  );
  return { rollup: data, loading, error, refetch };
}

// ---------------------------------------------------------------------------
// Tracing – Agent Events (REST)
// ---------------------------------------------------------------------------

export function useAgentTrace(agentId: string): {
  events: TraceEvent[];
  loading: boolean;
  error: string | null;
  refetch: () => void;
} {
  const { data, loading, error, refetch } = useFetch(
    () => api.traceAgent(agentId),
    [agentId],
  );
  return { events: data ?? [], loading, error, refetch };
}

// ---------------------------------------------------------------------------
// Topology
// ---------------------------------------------------------------------------

export function useTopology(squadId: string): {
  topology: TopologyGetResponse | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
} {
  const { data, loading, error, refetch } = useFetch(
    () => api.getTopology(squadId),
    [squadId],
  );
  return { topology: data, loading, error, refetch };
}

// ---------------------------------------------------------------------------
// Tracing – Agent Events (WebSocket with HTTP polling fallback)
// ---------------------------------------------------------------------------

const WS_RECONNECT_DELAY_MS = 3_000;
const POLL_INTERVAL_MS = 5_000;

export function useAgentTraceWs(agentId: string): {
  events: TraceEvent[];
  connected: boolean;
  error: string | null;
} {
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Track whether we've fallen back to polling so we don't re-attempt WS.
  const usingPolling = useRef(false);
  const wsRef = useRef<WebSocket | null>(null);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    let cancelled = false;
    usingPolling.current = false;

    // Derive the WebSocket URL from the configured API base URL.
    const apiBase =
      typeof process !== 'undefined'
        ? process.env.NEXT_PUBLIC_API_URL ?? 'http://127.0.0.1:8090'
        : 'http://127.0.0.1:8090';
    const wsBase = apiBase.replace(/^http/, 'ws');
    const wsUrl = `${wsBase}/ws/tracing/agents/${encodeURIComponent(agentId)}`;

    // ---- Polling fallback --------------------------------------------------

    function startPolling() {
      if (cancelled) return;
      usingPolling.current = true;
      setConnected(false);

      const poll = () => {
        if (cancelled) return;
        api
          .traceAgent(agentId)
          .then((data) => {
            if (!cancelled) {
              setEvents(data);
              setError(null);
            }
          })
          .catch((err: unknown) => {
            if (!cancelled) {
              setError(err instanceof Error ? err.message : String(err));
            }
          });
      };

      // Immediate first poll.
      poll();
      pollTimerRef.current = setInterval(poll, POLL_INTERVAL_MS);
    }

    // ---- WebSocket ---------------------------------------------------------

    function connectWs() {
      if (cancelled || usingPolling.current) return;

      try {
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
          if (cancelled) {
            ws.close();
            return;
          }
          setConnected(true);
          setError(null);
        };

        ws.onmessage = (evt) => {
          if (cancelled) return;
          try {
            const parsed = JSON.parse(evt.data as string) as TraceEvent;
            setEvents((prev) => [...prev, parsed]);
          } catch {
            // If the payload is a batch array, handle that as well.
            try {
              const batch = JSON.parse(evt.data as string) as TraceEvent[];
              if (Array.isArray(batch)) {
                setEvents((prev) => [...prev, ...batch]);
              }
            } catch {
              // Non-JSON message – ignore.
            }
          }
        };

        ws.onerror = () => {
          if (cancelled) return;
          setConnected(false);
          setError('WebSocket connection error – falling back to HTTP polling');
          ws.close();
        };

        ws.onclose = () => {
          if (cancelled) return;
          setConnected(false);

          if (!usingPolling.current) {
            // First close → fall back to polling rather than endlessly retrying.
            startPolling();
          }
        };
      } catch {
        // WebSocket constructor can throw in non-browser environments.
        if (!cancelled) {
          startPolling();
        }
      }
    }

    connectWs();

    // ---- Cleanup -----------------------------------------------------------

    return () => {
      cancelled = true;

      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }

      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [agentId]);

  return { events, connected, error };
}
