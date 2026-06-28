"use client";

import { useEffect, useMemo, useState } from "react";
import { LogIn, Plug, RefreshCw, RotateCcw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Select } from "@/components/ui/select";

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8090").replace(/\/$/, "");

type Seat = {
  seat_id: string;
  tenant_id: string;
  vendor: "codex" | "claude" | "gemini" | "kiro";
  display_name: string | null;
  active: boolean;
  available: boolean;
};

type Session = {
  session_id: string;
  seat_id: string;
  tenant_id: string;
  vendor: string;
  status: string;
  status_reason: string | null;
  verification_uri: string | null;
  user_code: string | null;
  device_code_ref: string | null;
  expires_at: string | null;
  metadata: Record<string, unknown>;
};

export default function SessionsPage() {
  const [seats, setSeats] = useState<Seat[]>([]);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [selectedSeatId, setSelectedSeatId] = useState("");
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadAll() {
    setLoading(true);
    setError(null);
    try {
      const [seatData, sessionData] = await Promise.all([
        apiJson<{ seats: Seat[] }>("/seats"),
        apiJson<{ sessions: Session[] }>("/sessions"),
      ]);
      setSeats(seatData.seats);
      setSessions(sessionData.sessions);
      setSelectedSeatId((current) => current || seatData.seats[0]?.seat_id || "");
    } catch (err) {
      setError(messageFromError(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadAll();
  }, []);

  const selectedSeat = useMemo(
    () => seats.find((seat) => seat.seat_id === selectedSeatId) ?? null,
    [seats, selectedSeatId],
  );

  async function startLogin() {
    if (!selectedSeatId) return;
    setStarting(true);
    setError(null);
    try {
      const response = await fetch(`${API_URL}/sessions/device-login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ seat_id: selectedSeatId }),
      });
      const data = (await response.json()) as DeviceLoginResponse;
      if (!response.ok && data.detail?.session) {
        setError(data.detail.session.status_reason || data.detail.code);
      } else if (!response.ok) {
        throw new Error(data.detail?.code || `${response.status} ${response.statusText}`);
      }
      await loadAll();
    } catch (err) {
      setError(messageFromError(err));
    } finally {
      setStarting(false);
    }
  }

  async function renewSession(sessionId: string) {
    setError(null);
    try {
      const response = await fetch(`${API_URL}/sessions/${encodeURIComponent(sessionId)}/renew`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      const data = (await response.json()) as DeviceLoginResponse;
      if (!response.ok && data.detail?.session) {
        setError(data.detail.session.status_reason || data.detail.code);
      } else if (!response.ok) {
        throw new Error(data.detail?.code || `${response.status} ${response.statusText}`);
      }
      await loadAll();
    } catch (err) {
      setError(messageFromError(err));
    }
  }

  async function refreshStatus(sessionId: string) {
    setError(null);
    try {
      const data = await apiJson<{ session: Session }>(`/sessions/${encodeURIComponent(sessionId)}/status`);
      setSessions((current) => current.map((session) => (session.session_id === sessionId ? data.session : session)));
    } catch (err) {
      setError(messageFromError(err));
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-normal text-foreground">Sessions</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Start vendor device-login flows against registered isolated seats.
          </p>
        </div>
        <Button type="button" variant="outline" onClick={loadAll} disabled={loading}>
          <RefreshCw className="size-4" />
          Refresh
        </Button>
      </div>

      {error && (
        <div className="rounded-lg border border-warning/40 bg-warning/10 p-4 text-sm text-warning">
          {error}
        </div>
      )}

      <div className="rounded-lg border border-border bg-card p-4 shadow-sm">
        <div className="mb-4 flex items-center gap-2 text-sm font-semibold">
          <LogIn className="size-4" />
          Device login
        </div>
        {seats.length === 0 ? (
          <EmptyState
            icon={Plug}
            title="No seats available"
            description="Register a seat before starting a vendor OAuth/device-login session."
          />
        ) : (
          <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_auto]">
            <Select
              aria-label="Seat"
              value={selectedSeatId}
              onChange={(event) => setSelectedSeatId(event.target.value)}
            >
              {seats.map((seat) => (
                <option key={seat.seat_id} value={seat.seat_id}>
                  {seat.display_name || seat.seat_id} / {seat.vendor}
                </option>
              ))}
            </Select>
            <Button type="button" onClick={startLogin} disabled={!selectedSeat || !selectedSeat.active || starting}>
              <LogIn className="size-4" />
              {starting ? "Starting" : "Start login"}
            </Button>
          </div>
        )}
      </div>

      {loading ? (
        <div className="h-64 animate-pulse rounded-lg border border-border bg-card" />
      ) : sessions.length === 0 ? (
        <EmptyState
          icon={Plug}
          title="No sessions recorded"
          description="Device-login attempts and their persisted status will appear here."
        />
      ) : (
        <div className="space-y-3">
          {sessions.map((session) => (
            <article key={session.session_id} className="rounded-lg border border-border bg-card p-4 shadow-sm">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="truncate text-sm font-semibold">{session.seat_id}</h2>
                    <SessionStatus status={session.status} />
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    {session.tenant_id} / {session.vendor} / {session.session_id}
                  </div>
                </div>
                <div className="flex gap-1">
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    aria-label="Refresh status"
                    onClick={() => refreshStatus(session.session_id)}
                  >
                    <RefreshCw className="size-4" />
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    aria-label="Renew session"
                    onClick={() => renewSession(session.session_id)}
                  >
                    <RotateCcw className="size-4" />
                  </Button>
                </div>
              </div>

              <div className="mt-4 grid gap-3 text-sm md:grid-cols-2">
                <Field label="Verification" value={session.verification_uri} asLink />
                <Field label="User code" value={session.user_code} mono />
                <Field label="Device ref" value={session.device_code_ref} mono />
                <Field label="Expires" value={session.expires_at ? new Date(session.expires_at).toLocaleString() : null} />
              </div>
              {session.status_reason && (
                <div className="mt-3 rounded-md border border-border bg-muted px-3 py-2 text-xs text-muted-foreground">
                  {session.status_reason}
                </div>
              )}
            </article>
          ))}
        </div>
      )}
    </div>
  );
}

type DeviceLoginResponse =
  | { session: Session; detail?: never }
  | { detail?: { code: string; session?: Session } };

function SessionStatus({ status }: { status: string }) {
  const className =
    status === "pending"
      ? "border-warning/30 bg-warning/10 text-warning"
      : status === "authenticated"
        ? "border-success/30 bg-success/10 text-success"
        : status === "degraded" || status === "expired"
          ? "border-destructive/30 bg-destructive/10 text-destructive"
          : "border-muted bg-muted text-muted-foreground";
  return <span className={`rounded-full border px-2 py-0.5 text-xs font-medium ${className}`}>{status}</span>;
}

function Field({
  label,
  value,
  mono = false,
  asLink = false,
}: {
  label: string;
  value: string | null;
  mono?: boolean;
  asLink?: boolean;
}) {
  return (
    <div className="min-w-0">
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      {value && asLink ? (
        <a className="mt-1 block truncate text-sm text-primary underline-offset-4 hover:underline" href={value} target="_blank" rel="noreferrer">
          {value}
        </a>
      ) : (
        <div className={`mt-1 min-h-5 break-all text-sm text-foreground ${mono ? "font-mono" : ""}`}>
          {value || "None"}
        </div>
      )}
    </div>
  );
}

async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  const text = await response.text();
  const data = text ? (JSON.parse(text) as unknown) : null;
  if (!response.ok) {
    throw new Error(extractApiError(data) || `${response.status} ${response.statusText}`);
  }
  return data as T;
}

function extractApiError(data: unknown): string | null {
  if (!data || typeof data !== "object" || !("detail" in data)) return null;
  const detail = (data as { detail: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && "code" in detail) return String((detail as { code: unknown }).code);
  return null;
}

function messageFromError(err: unknown) {
  return err instanceof Error ? err.message : String(err);
}
