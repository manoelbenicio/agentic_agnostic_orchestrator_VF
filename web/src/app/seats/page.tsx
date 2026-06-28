"use client";

import { FormEvent, ReactNode, useEffect, useMemo, useState } from "react";
import { KeyRound, Pencil, Plus, RefreshCw, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8090").replace(/\/$/, "");
const vendors = ["codex", "claude", "gemini", "kiro"] as const;
type Vendor = (typeof vendors)[number];

type Seat = {
  seat_id: string;
  tenant_id: string;
  vendor: Vendor;
  home_dir: string;
  config_dir: string;
  display_name: string | null;
  active: boolean;
  available: boolean;
  leased: boolean;
  ref_count: number;
  metadata: Record<string, unknown>;
};

type SeatForm = {
  seat_id: string;
  tenant_id: string;
  vendor: Vendor;
  home_dir: string;
  config_dir: string;
  display_name: string;
};

const emptyForm: SeatForm = {
  seat_id: "",
  tenant_id: "",
  vendor: "codex",
  home_dir: "",
  config_dir: "",
  display_name: "",
};

export default function SeatsPage() {
  const [seats, setSeats] = useState<Seat[]>([]);
  const [form, setForm] = useState<SeatForm>(emptyForm);
  const [editingSeatId, setEditingSeatId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadSeats() {
    setLoading(true);
    setError(null);
    try {
      const data = await apiJson<{ seats: Seat[] }>("/seats");
      setSeats(data.seats);
    } catch (err) {
      setError(messageFromError(err));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadSeats();
  }, []);

  const counts = useMemo(
    () => ({
      total: seats.length,
      available: seats.filter((seat) => seat.available).length,
      leased: seats.filter((seat) => seat.leased).length,
      inactive: seats.filter((seat) => !seat.active).length,
    }),
    [seats],
  );

  async function submitSeat(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const body = {
        tenant_id: form.tenant_id,
        vendor: form.vendor,
        home_dir: form.home_dir,
        config_dir: form.config_dir,
        display_name: form.display_name || null,
      };
      if (editingSeatId) {
        await apiJson(`/seats/${encodeURIComponent(editingSeatId)}`, {
          method: "PATCH",
          body: JSON.stringify(body),
        });
      } else {
        await apiJson("/seats", {
          method: "POST",
          body: JSON.stringify({ seat_id: form.seat_id, ...body }),
        });
      }
      setForm(emptyForm);
      setEditingSeatId(null);
      await loadSeats();
    } catch (err) {
      setError(messageFromError(err));
    } finally {
      setSaving(false);
    }
  }

  function editSeat(seat: Seat) {
    setEditingSeatId(seat.seat_id);
    setForm({
      seat_id: seat.seat_id,
      tenant_id: seat.tenant_id,
      vendor: seat.vendor,
      home_dir: seat.home_dir,
      config_dir: seat.config_dir,
      display_name: seat.display_name ?? "",
    });
  }

  async function toggleSeat(seat: Seat) {
    setError(null);
    try {
      await apiJson(`/seats/${encodeURIComponent(seat.seat_id)}`, {
        method: "PATCH",
        body: JSON.stringify({ active: !seat.active }),
      });
      await loadSeats();
    } catch (err) {
      setError(messageFromError(err));
    }
  }

  async function removeSeat(seatId: string) {
    setError(null);
    try {
      await apiJson(`/seats/${encodeURIComponent(seatId)}`, { method: "DELETE" });
      await loadSeats();
      if (editingSeatId === seatId) {
        setEditingSeatId(null);
        setForm(emptyForm);
      }
    } catch (err) {
      setError(messageFromError(err));
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-normal text-foreground">Seats</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Provision isolated vendor seats with per-seat HOME and config paths.
          </p>
        </div>
        <Button type="button" variant="outline" onClick={loadSeats} disabled={loading}>
          <RefreshCw className="size-4" />
          Refresh
        </Button>
      </div>

      {error && (
        <div className="rounded-lg border border-destructive/40 bg-destructive/10 p-4 text-sm text-destructive">
          {error}
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="Total" value={counts.total} />
        <Metric label="Available" value={counts.available} />
        <Metric label="Leased" value={counts.leased} />
        <Metric label="Inactive" value={counts.inactive} />
      </div>

      <form onSubmit={submitSeat} className="rounded-lg border border-border bg-card p-4 shadow-sm">
        <div className="mb-4 flex items-center gap-2 text-sm font-semibold">
          {editingSeatId ? <Pencil className="size-4" /> : <Plus className="size-4" />}
          {editingSeatId ? "Edit seat" : "Register seat"}
        </div>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          <LabeledControl label="Seat ID">
            <Input
              aria-label="Seat ID"
              value={form.seat_id}
              disabled={Boolean(editingSeatId)}
              onChange={(event) => setForm((current) => ({ ...current, seat_id: event.target.value }))}
              required
            />
          </LabeledControl>
          <LabeledControl label="Tenant ID">
            <Input
              aria-label="Tenant ID"
              value={form.tenant_id}
              onChange={(event) => setForm((current) => ({ ...current, tenant_id: event.target.value }))}
              required
            />
          </LabeledControl>
          <LabeledControl label="Vendor">
            <Select
              aria-label="Vendor"
              value={form.vendor}
              onChange={(event) => setForm((current) => ({ ...current, vendor: event.target.value as Vendor }))}
            >
              {vendors.map((vendor) => (
                <option key={vendor} value={vendor}>
                  {vendor}
                </option>
              ))}
            </Select>
          </LabeledControl>
          <LabeledControl label="Home directory">
            <Input
              aria-label="Home directory"
              value={form.home_dir}
              onChange={(event) => setForm((current) => ({ ...current, home_dir: event.target.value }))}
              required
            />
          </LabeledControl>
          <LabeledControl label="Config directory">
            <Input
              aria-label="Config directory"
              value={form.config_dir}
              onChange={(event) => setForm((current) => ({ ...current, config_dir: event.target.value }))}
              required
            />
          </LabeledControl>
          <LabeledControl label="Display name">
            <Input
              aria-label="Display name"
              value={form.display_name}
              onChange={(event) => setForm((current) => ({ ...current, display_name: event.target.value }))}
            />
          </LabeledControl>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button type="submit" disabled={saving}>
            <KeyRound className="size-4" />
            {saving ? "Saving" : editingSeatId ? "Update" : "Register"}
          </Button>
          {editingSeatId && (
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                setEditingSeatId(null);
                setForm(emptyForm);
              }}
            >
              Cancel
            </Button>
          )}
        </div>
      </form>

      {loading ? (
        <div className="h-64 animate-pulse rounded-lg border border-border bg-card" />
      ) : seats.length === 0 ? (
        <EmptyState
          icon={KeyRound}
          title="No seats configured"
          description="Register a seat to make vendor sessions available. The control-plane does not create default seats."
        />
      ) : (
        <div className="grid gap-3 xl:grid-cols-2">
          {seats.map((seat) => (
            <article key={seat.seat_id} className="rounded-lg border border-border bg-card p-4 shadow-sm">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="truncate text-sm font-semibold">{seat.display_name || seat.seat_id}</h2>
                    <StatusBadge seat={seat} />
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    {seat.tenant_id} / {seat.vendor}
                  </div>
                </div>
                <div className="flex gap-1">
                  <Button type="button" variant="ghost" size="icon" aria-label="Edit seat" onClick={() => editSeat(seat)}>
                    <Pencil className="size-4" />
                  </Button>
                  <Button type="button" variant="ghost" size="icon" aria-label="Toggle active seat" onClick={() => toggleSeat(seat)}>
                    <RefreshCw className="size-4" />
                  </Button>
                  <Button type="button" variant="ghost" size="icon" aria-label="Remove seat" onClick={() => removeSeat(seat.seat_id)}>
                    <Trash2 className="size-4" />
                  </Button>
                </div>
              </div>
              <dl className="mt-4 grid gap-2 text-xs">
                <PathRow label="HOME" value={seat.home_dir} />
                <PathRow label="Config" value={seat.config_dir} />
                <PathRow label="Active sessions" value={String(seat.ref_count)} />
              </dl>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-border bg-card p-4 shadow-sm">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums">{value}</div>
    </div>
  );
}

function LabeledControl({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="grid gap-1.5 text-xs font-medium text-muted-foreground">
      {label}
      {children}
    </label>
  );
}

function StatusBadge({ seat }: { seat: Seat }) {
  const label = !seat.active ? "inactive" : seat.leased ? "leased" : "available";
  const className = !seat.active
    ? "border-muted bg-muted text-muted-foreground"
    : seat.leased
      ? "border-warning/30 bg-warning/10 text-warning"
      : "border-success/30 bg-success/10 text-success";
  return <span className={`rounded-full border px-2 py-0.5 text-xs font-medium ${className}`}>{label}</span>;
}

function PathRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid gap-1 sm:grid-cols-[90px_minmax(0,1fr)]">
      <dt className="font-medium text-muted-foreground">{label}</dt>
      <dd className="min-w-0 break-all font-mono text-muted-foreground">{value}</dd>
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
  if (Array.isArray(detail)) return detail.map((item) => (typeof item === "object" && item && "msg" in item ? String(item.msg) : String(item))).join("; ");
  return null;
}

function messageFromError(err: unknown) {
  return err instanceof Error ? err.message : String(err);
}
