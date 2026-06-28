"use client";

import React, { useEffect, useState } from "react";
import { 
  Users, 
  UserPlus, 
  Trash2, 
  RefreshCw, 
  Brain, 
  Server, 
  Activity, 
  AlertCircle,
  Plus,
  ShieldCheck,
  Cpu,
  Loader2
} from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";

type Agent = {
  agent_id: string;
  tenant_id: string;
  label: string;
  vendor: string;
  role: string;
  status: string;
  workspace_id: string | null;
  pane_id: string | null;
  stable_key: string | null;
  metadata: Record<string, any>;
};

const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8090";

const blankForm = {
  tenant_id: "tenant-a",
  label: "",
  vendor: "gemini",
  role: "worker",
  workspace_id: "",
  pane_id: "",
  stable_key: "",
};

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState(blankForm);
  const [showAddForm, setShowAddForm] = useState(false);
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  useEffect(() => {
    let active = true;

    async function loadAgents() {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(`${apiBase}/agents`, {
          cache: "no-store",
          headers: { Accept: "application/json" }
        });
        if (!response.ok) throw new Error(`GET /agents returned ${response.status}`);
        const data = (await response.json()) as Agent[];
        if (active) {
          setAgents(data);
        }
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : String(err));
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    loadAgents();
    return () => {
      active = false;
    };
  }, [refreshTrigger]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.label.trim()) return;

    setSaving(true);
    setError(null);

    const payload = {
      tenant_id: form.tenant_id.trim(),
      label: form.label.trim(),
      vendor: form.vendor.trim(),
      role: form.role.trim(),
      workspace_id: form.workspace_id.trim() || null,
      pane_id: form.pane_id.trim() || null,
      stable_key: form.stable_key.trim() || null,
      metadata: {}
    };

    try {
      const response = await fetch(`${apiBase}/agents`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        const errBody = await response.json().catch(() => ({}));
        throw new Error(errBody.detail?.reason || `POST /agents returned ${response.status}`);
      }

      setForm(blankForm);
      setShowAddForm(false);
      setRefreshTrigger((prev) => prev + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(agentId: string) {
    if (!confirm(`Tem certeza de que deseja remover o agente ${agentId}?`)) return;

    setError(null);
    try {
      const response = await fetch(`${apiBase}/agents/${encodeURIComponent(agentId)}`, {
        method: "DELETE",
        headers: { Accept: "application/json" }
      });

      if (!response.ok) {
        const errBody = await response.json().catch(() => ({}));
        throw new Error(errBody.detail?.reason || `DELETE /agents returned ${response.status}`);
      }

      setRefreshTrigger((prev) => prev + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <div className="space-y-6 aop-fade-in">
      {/* Page Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="mb-1 inline-flex items-center gap-2 rounded-md border border-border bg-muted px-2.5 py-1 text-xs font-medium text-muted-foreground">
            <Users className="size-3.5 text-accent animate-pulse" />
            Agent Registry CRUD
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-foreground">
            Squad Agent Members
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Register and coordinate runtime workers, roles, and status checks.
          </p>
        </div>
        
        <div className="flex items-center gap-2">
          <Button
            onClick={() => setShowAddForm(!showAddForm)}
            variant={showAddForm ? "outline" : "default"}
            className="flex items-center gap-2"
          >
            <UserPlus className="size-4" />
            {showAddForm ? "Cancelar" : "Registrar Agente"}
          </Button>

          <button
            onClick={() => setRefreshTrigger((prev) => prev + 1)}
            disabled={loading}
            className="flex h-10 w-10 items-center justify-center rounded-lg border border-border bg-card text-foreground shadow-sm transition-all hover:bg-muted active:scale-95"
            title="Recarregar agentes"
          >
            <RefreshCw className={`size-4 ${loading ? "animate-spin" : ""}`} />
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-3 rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive aop-float-in">
          <AlertCircle className="size-5 shrink-0" />
          <div className="font-medium">{error}</div>
        </div>
      )}

      {/* Add Agent Form/Card */}
      {showAddForm && (
        <Card className="aop-float-in border-accent/40 shadow-lg">
          <CardHeader>
            <CardTitle>Registrar Novo Agente</CardTitle>
            <CardDescription>
              Adicione um novo agente de inteligência ao pool canônico da AOP.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-1">
                  <label className="text-xs font-semibold text-muted-foreground">Nome (Label)</label>
                  <Input
                    required
                    placeholder="Ex: Codex Senior Coder"
                    value={form.label}
                    onChange={(e) => setForm({ ...form, label: e.target.value })}
                  />
                </div>

                <div className="space-y-1">
                  <label className="text-xs font-semibold text-muted-foreground">Provedor (Vendor)</label>
                  <Select
                    value={form.vendor}
                    onChange={(e) => setForm({ ...form, vendor: e.target.value })}
                  >
                    <option value="codex">Codex</option>
                    <option value="gemini">Gemini</option>
                    <option value="claude">Claude</option>
                    <option value="kiro">Kiro</option>
                    <option value="nemotron">Nemotron</option>
                  </Select>
                </div>

                <div className="space-y-1">
                  <label className="text-xs font-semibold text-muted-foreground">Papel Padrão (Role)</label>
                  <Select
                    value={form.role}
                    onChange={(e) => setForm({ ...form, role: e.target.value })}
                  >
                    <option value="worker">Worker</option>
                    <option value="tech-lead">Tech-Lead</option>
                  </Select>
                </div>

                <div className="space-y-1">
                  <label className="text-xs font-semibold text-muted-foreground">Tenant ID</label>
                  <Input
                    required
                    value={form.tenant_id}
                    onChange={(e) => setForm({ ...form, tenant_id: e.target.value })}
                  />
                </div>

                <div className="space-y-1">
                  <label className="text-xs font-semibold text-muted-foreground">Workspace ID (Opcional)</label>
                  <Input
                    placeholder="Ex: workspace-default"
                    value={form.workspace_id}
                    onChange={(e) => setForm({ ...form, workspace_id: e.target.value })}
                  />
                </div>

                <div className="space-y-1">
                  <label className="text-xs font-semibold text-muted-foreground">Pane ID / Terminal (Opcional)</label>
                  <Input
                    placeholder="Ex: w8:pG"
                    value={form.pane_id}
                    onChange={(e) => setForm({ ...form, pane_id: e.target.value })}
                  />
                </div>

                <div className="space-y-1">
                  <label className="text-xs font-semibold text-muted-foreground">Stable Auth Key (Opcional)</label>
                  <Input
                    placeholder="Ex: secret-auth-token"
                    value={form.stable_key}
                    onChange={(e) => setForm({ ...form, stable_key: e.target.value })}
                  />
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <Button type="button" variant="outline" onClick={() => setShowAddForm(false)}>
                  Cancelar
                </Button>
                <Button type="submit" variant="default" disabled={saving}>
                  {saving ? "Salvando..." : "Salvar Agente"}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {/* Agents Listing */}
      <Card>
        <CardHeader>
          <CardTitle>Pool de Agentes Ativos</CardTitle>
          <CardDescription>
            Lista de nós e runtimes operacionais reconhecidos pelo control-plane.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {loading && agents.length === 0 ? (
            <div className="flex items-center justify-center py-12 text-muted-foreground">
              <Loader2 className="size-6 animate-spin text-accent" />
              <span className="text-sm ml-2">Buscando agentes...</span>
            </div>
          ) : agents.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center text-muted-foreground">
              <Brain className="mb-2 size-10 opacity-30 animate-pulse" />
              <p className="text-sm font-semibold">Nenhum agente ativo registrado</p>
              <p className="text-xs opacity-60 mt-1">Utilize o botão acima para registrar um agente.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm border-collapse">
                <thead>
                  <tr className="border-b border-border text-xs font-semibold uppercase tracking-wider text-muted-foreground bg-muted/30">
                    <th className="py-3 px-4">Identificador / Label</th>
                    <th className="py-3 px-4">Vendor</th>
                    <th className="py-3 px-4">Papel (Role)</th>
                    <th className="py-3 px-4">Status / Saúde</th>
                    <th className="py-3 px-4">Terminal / Pane</th>
                    <th className="py-3 px-4 text-right">Ações</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {agents.map((a) => (
                    <tr key={a.agent_id} className="hover:bg-muted/15 transition-colors duration-150">
                      <td className="py-3 px-4">
                        <div className="flex items-center gap-2">
                          <Cpu className="size-4 text-accent shrink-0" />
                          <div>
                            <span className="font-semibold text-foreground">{a.label}</span>
                            <span className="block font-mono text-[10px] text-muted-foreground">
                              id: {a.agent_id}
                            </span>
                          </div>
                        </div>
                      </td>
                      <td className="py-3 px-4">
                        <Badge variant="outline" className="uppercase font-semibold text-[10px]">
                          {a.vendor}
                        </Badge>
                      </td>
                      <td className="py-3 px-4 text-xs font-semibold uppercase">
                        {a.role === "tech-lead" ? (
                          <div className="flex items-center gap-1 text-accent">
                            <ShieldCheck className="size-3.5" />
                            Tech-Lead
                          </div>
                        ) : (
                          <span className="text-muted-foreground">Worker</span>
                        )}
                      </td>
                      <td className="py-3 px-4">
                        <div className="flex items-center gap-1.5">
                          <span className={`size-2 rounded-full ${
                            a.status === "active" || a.status === "healthy" 
                              ? "bg-success animate-pulse" 
                              : "bg-warning"
                          }`} />
                          <span className="text-xs uppercase font-medium">{a.status}</span>
                        </div>
                      </td>
                      <td className="py-3 px-4 font-mono text-xs text-muted-foreground">
                        {a.pane_id || "N/A"}
                      </td>
                      <td className="py-3 px-4 text-right">
                        <button
                          onClick={() => handleDelete(a.agent_id)}
                          className="p-2 rounded-lg border border-border text-destructive hover:bg-destructive/10 hover:border-destructive/30 transition-all active:scale-95"
                          title="Remover Agente"
                        >
                          <Trash2 className="size-4" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
