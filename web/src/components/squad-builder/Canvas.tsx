"use client";

import React, { useCallback, useEffect, useState, useMemo } from "react";
import {
  ReactFlow,
  useNodesState,
  useEdgesState,
  addEdge,
  MiniMap,
  Controls,
  Background,
  type Connection,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { api } from "@/lib/api-client";
import type { Agent, Seat } from "@/lib/api-types";
import {
  Download,
  Loader2,
  Plus,
  Save,
  AlertCircle,
  CheckCircle2,
  Trash2,
  UserCheck,
  ShieldAlert,
  Server
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const SQUAD_ID = "default";

type SaveState = "idle" | "saving" | "saved" | "error";
type SquadNodeData = Record<string, unknown> & {
  label: string;
  role: string;
  vendor: string;
};
type SquadNode = Node<SquadNodeData>;

export default function Canvas() {
  const [nodes, setNodes, onNodesChange] = useNodesState<SquadNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [seats, setSeats] = useState<Seat[]>([]);
  const [loading, setLoading] = useState(true);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  // Load topology + agents on mount
  const loadTopology = useCallback(async (cancelled = false) => {
    try {
      const [topoRes, agentList, seatRes] = await Promise.all([
        api.getTopology(SQUAD_ID).catch(() => null),
        api.listAgents().catch(() => [] as Agent[]),
        api.getSeats().catch(() => ({ seats: [] as Seat[] })),
      ]);

      if (cancelled) return;
      setAgents(agentList);
      setSeats(seatRes.seats);

      // If topology has stored nodes/edges, use them
      const stored = topoRes?.stored as {
        nodes?: Array<Record<string, unknown>>;
        edges?: Array<Record<string, unknown>>;
      } | null;

      if (stored?.nodes && stored.nodes.length > 0) {
        setNodes(normalizeStoredNodes(stored.nodes, agentList));
        setEdges(normalizeStoredEdges(stored.edges ?? []));
      } else {
        // Generate initial canvas from registered agents
        const initialNodes: SquadNode[] = agentList.map((agent, i) => ({
          id: agent.agent_id,
          position: {
            x: 150 + (i % 3) * 250,
            y: 80 + Math.floor(i / 3) * 150,
          },
          data: {
            label: agent.label,
            role: agent.role,
            vendor: agent.vendor,
          },
        }));
        setNodes(initialNodes);
        setEdges([]);
      }
    } catch (err) {
      if (!cancelled)
        setLoadError(
          err instanceof Error ? err.message : "Failed to load topology",
        );
    } finally {
      if (!cancelled) setLoading(false);
    }
  }, [setNodes, setEdges]);

  useEffect(() => {
    let cancelled = false;
    loadTopology(cancelled);
    return () => {
      cancelled = true;
    };
  }, [loadTopology]);

  const onConnect = useCallback(
    (params: Connection | Edge) =>
      setEdges((eds) => addEdge({ ...params, animated: true }, eds)),
    [setEdges],
  );

  // Save topology to endpoint
  const handleSave = useCallback(async () => {
    setSaveState("saving");
    try {
      const nodeData = nodes.map((n) => ({
        id: n.id,
        label: String(n.data.label ?? n.id),
        role: String(n.data.role ?? "worker"),
        vendor: String(n.data.vendor ?? "unknown"),
        x: String(n.position.x),
        y: String(n.position.y),
      }));
      const edgeData = edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
      }));
      await api.saveTopology(SQUAD_ID, {
        nodes: nodeData,
        edges: edgeData,
      });
      setSaveState("saved");
      setTimeout(() => setSaveState("idle"), 2000);
    } catch {
      setSaveState("error");
      setTimeout(() => setSaveState("idle"), 3000);
    }
  }, [nodes, edges]);

  // Add agent node that isn't on canvas yet
  const handleAddAgent = useCallback(
    (agent: Agent) => {
      const exists = nodes.some((n) => n.id === agent.agent_id);
      if (exists) return;
      const newNode: SquadNode = {
        id: agent.agent_id,
        position: {
          x: 200 + Math.random() * 150,
          y: 100 + Math.random() * 150,
        },
        data: { 
          label: agent.label, 
          role: agent.role,
          vendor: agent.vendor
        },
      };
      setNodes((nds) => [...nds, newNode]);
    },
    [nodes, setNodes],
  );

  // Exclude node from canvas
  const handleDeleteNode = useCallback((nodeId: string) => {
    setNodes((nds) => nds.filter((n) => n.id !== nodeId));
    setEdges((eds) => eds.filter((e) => e.source !== nodeId && e.target !== nodeId));
    if (selectedNodeId === nodeId) {
      setSelectedNodeId(null);
    }
  }, [selectedNodeId, setNodes, setEdges]);

  // Modify node role (worker <-> tech-lead)
  const handleToggleRole = useCallback((nodeId: string) => {
    setNodes((nds) =>
      nds.map((n) => {
        if (n.id === nodeId) {
          const currentRole = n.data.role;
          const nextRole = currentRole === "tech-lead" ? "worker" : "tech-lead";
          return {
            ...n,
            data: {
              ...n.data,
              role: nextRole,
            },
          };
        }
        return n;
      })
    );
  }, [setNodes]);

  // Compute vendor breakdown
  const vendorCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    nodes.forEach((n) => {
      const vendor = n.data.vendor || "unknown";
      counts[vendor] = (counts[vendor] || 0) + 1;
    });
    return counts;
  }, [nodes]);

  const unplacedAgents = agents.filter(
    (a) => !nodes.some((n) => n.id === a.agent_id),
  );

  const selectedNode = useMemo(() => {
    return nodes.find((n) => n.id === selectedNodeId);
  }, [nodes, selectedNodeId]);

  if (loading) {
    return (
      <div className="flex h-[80vh] items-center justify-center rounded-lg border border-border bg-card">
        <div className="flex items-center gap-3 text-muted-foreground">
          <Loader2 className="size-5 animate-spin text-accent" />
          <span className="text-sm">Loading topology…</span>
        </div>
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="flex h-[80vh] flex-col items-center justify-center rounded-lg border border-destructive/30 bg-destructive/5">
        <AlertCircle className="mb-3 size-8 text-destructive animate-bounce" />
        <p className="text-sm font-medium text-destructive">
          Failed to load topology
        </p>
        <p className="mt-1 text-xs text-muted-foreground">{loadError}</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Vendor Stats Dashboard Panel */}
      <div className="grid gap-3 sm:grid-cols-2 md:grid-cols-4">
        {Object.entries(vendorCounts).map(([vendor, count]) => (
          <div key={vendor} className="rounded-lg border border-border bg-card px-4 py-3 flex justify-between items-center shadow-sm">
            <span className="text-xs font-semibold uppercase text-muted-foreground">{vendor}</span>
            <Badge variant="accent" className="font-mono">{count}</Badge>
          </div>
        ))}
        {Object.keys(vendorCounts).length === 0 && (
          <div className="col-span-full text-center py-2 text-xs text-muted-foreground border border-dashed border-border rounded-lg bg-card/40">
            Nenhum agente colocado no canvas.
          </div>
        )}
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
        <div className="space-y-3">
          {/* Canvas Toolbar */}
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-border bg-card px-4 py-2">
            <div className="flex flex-wrap items-center gap-2">
              {unplacedAgents.length > 0 ? (
                <>
                  <span className="text-xs font-medium text-muted-foreground">
                    Colocar agente:
                  </span>
                  {unplacedAgents.map((agent) => (
                    <button
                      key={agent.agent_id}
                      onClick={() => handleAddAgent(agent)}
                      className="flex items-center gap-1 rounded-md border border-border bg-background px-2.5 py-1 text-xs font-semibold transition-all hover:border-primary/50 hover:bg-muted"
                    >
                      <Plus className="size-3" />
                      {agent.label}
                    </button>
                  ))}
                </>
              ) : (
                <span className="text-xs text-muted-foreground">Todos os agentes já estão no canvas</span>
              )}
            </div>
            
            <button
              onClick={handleSave}
              disabled={saveState === "saving"}
              className={`flex items-center gap-2 rounded-md px-3 py-1.5 text-xs font-semibold shadow-sm transition-all active:scale-95 ${
                saveState === "saved"
                  ? "bg-success/15 text-success border border-success/30"
                  : saveState === "error"
                    ? "bg-destructive/15 text-destructive border border-destructive/30"
                    : "bg-primary text-primary-foreground hover:bg-primary/95"
              }`}
            >
              {saveState === "saving" ? (
                <Loader2 className="size-3.5 animate-spin" />
              ) : saveState === "saved" ? (
                <CheckCircle2 className="size-3.5" />
              ) : saveState === "error" ? (
                <AlertCircle className="size-3.5" />
              ) : (
                <Save className="size-3.5" />
              )}
              {saveState === "saving"
                ? "Sincronizando..."
                : saveState === "saved"
                  ? "Salvo (ACL atualizada)!"
                  : saveState === "error"
                    ? "Falha ao salvar"
                    : "Salvar Topologia"}
            </button>
          </div>

          {/* Canvas ReactFlow */}
          <div
            style={{ width: "100%", height: "70vh" }}
            className="overflow-hidden rounded-lg border border-border bg-background"
          >
            <ReactFlow
              nodes={nodes}
              edges={edges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              onNodeClick={(_, node) => setSelectedNodeId(node.id)}
              onPaneClick={() => setSelectedNodeId(null)}
              fitView
            >
              <Controls />
              <MiniMap />
              <Background gap={12} size={1} />
            </ReactFlow>
          </div>
        </div>

        {/* Sidebar Settings Panel */}
        <aside className="space-y-4">
          {/* Node Actions Card */}
          {selectedNode ? (
            <Card className="border-accent/40 shadow-md aop-float-in">
              <CardHeader className="pb-3 border-b border-border">
                <CardTitle className="text-sm font-bold flex items-center justify-between">
                  <span>Gerenciar Nó</span>
                  <Badge variant="outline">{selectedNode.data.vendor}</Badge>
                </CardTitle>
                <CardDescription className="font-mono text-xs">{selectedNode.id}</CardDescription>
              </CardHeader>
              <CardContent className="pt-4 space-y-4">
                <div>
                  <label className="text-xs font-semibold uppercase text-muted-foreground block mb-2">
                    Papel na Topologia
                  </label>
                  <div className="flex gap-2">
                    <button
                      onClick={() => handleToggleRole(selectedNode.id)}
                      className={`flex-1 flex items-center justify-center gap-1.5 py-2 px-3 text-xs font-semibold rounded-lg border transition-all ${
                        selectedNode.data.role === "tech-lead"
                          ? "bg-accent/15 border-accent text-accent"
                          : "bg-background border-border text-muted-foreground hover:bg-muted"
                      }`}
                    >
                      <UserCheck className="size-3.5" />
                      Tech-Lead
                    </button>
                    <button
                      onClick={() => handleToggleRole(selectedNode.id)}
                      className={`flex-1 flex items-center justify-center gap-1.5 py-2 px-3 text-xs font-semibold rounded-lg border transition-all ${
                        selectedNode.data.role === "worker"
                          ? "bg-primary/10 border-primary text-primary"
                          : "bg-background border-border text-muted-foreground hover:bg-muted"
                      }`}
                    >
                      Worker
                    </button>
                  </div>
                </div>

                <div className="pt-2">
                  <button
                    onClick={() => handleDeleteNode(selectedNode.id)}
                    className="w-full flex items-center justify-center gap-2 py-2.5 px-3 rounded-lg border border-destructive bg-destructive/10 text-destructive text-xs font-semibold hover:bg-destructive/15 transition-all"
                  >
                    <Trash2 className="size-4" />
                    Excluir do Canvas
                  </button>
                </div>
              </CardContent>
            </Card>
          ) : (
            <div className="rounded-lg border border-dashed border-border p-6 text-center text-muted-foreground bg-card/25">
              <Server className="size-8 mx-auto mb-2 opacity-35" />
              <p className="text-xs">Selecione um nó no canvas para configurar papel ou excluir do grafo.</p>
            </div>
          )}

          {/* Connected Registry info */}
          <div className="rounded-lg border border-border bg-card p-4">
            <div className="text-sm font-semibold">Fila de Agentes</div>
            <div className="mt-3 space-y-2 max-h-48 overflow-y-auto">
              {agents.length ? agents.map((agent) => (
                <div key={agent.agent_id} className="rounded-md border border-border/60 bg-background/50 p-2.5 text-xs">
                  <div className="font-semibold text-foreground">{agent.label}</div>
                  <div className="mt-0.5 text-muted-foreground uppercase text-[10px]">
                    {agent.vendor} • {agent.role} • {agent.status}
                  </div>
                </div>
              )) : <div className="text-xs text-muted-foreground">Nenhum agente registrado.</div>}
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}

function normalizeStoredNodes(items: Array<Record<string, any>>, agents: Agent[]): SquadNode[] {
  const byId = new Map(agents.map((agent) => [agent.agent_id, agent]));
  return items.map((item, index) => {
    const id = String(item.id ?? `node-${index + 1}`);
    const agent = byId.get(id);
    return {
      id,
      position: {
        x: Number(item.x ?? 150 + (index % 3) * 250),
        y: Number(item.y ?? 80 + Math.floor(index / 3) * 150),
      },
      data: {
        label: String(item.label ?? agent?.label ?? id),
        role: String(item.role ?? agent?.role ?? "worker"),
        vendor: String(item.vendor ?? agent?.vendor ?? "unknown"),
      },
    };
  });
}

function normalizeStoredEdges(items: Array<Record<string, any>>): Edge[] {
  return items
    .filter((item) => item.source && item.target)
    .map((item, index) => ({
      id: String(item.id ?? `${item.source}-${item.target}-${index}`),
      source: String(item.source),
      target: String(item.target),
      animated: true,
    }));
}
