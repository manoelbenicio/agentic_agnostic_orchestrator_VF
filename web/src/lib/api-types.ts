// ---------------------------------------------------------------------------
// AOP Control-Plane – API Type Contracts
// ---------------------------------------------------------------------------

// Health -------------------------------------------------------------------

export interface HealthResponse {
  status: string;
}

export interface ReadyResponse {
  status: string;
  checks: {
    postgres: boolean;
    redis: boolean;
  };
}

// Agent --------------------------------------------------------------------

export interface Agent {
  agent_id: string;
  tenant_id: string;
  label: string;
  vendor: string;
  role: string;
  status: string;
  workspace_id: string | null;
  pane_id: string | null;
  stable_key: string | null;
  metadata: Record<string, unknown>;
}

export interface AgentCreateRequest {
  tenant_id: string;
  label: string;
  vendor: string;
  role: string;
  workspace_id?: string | null;
  pane_id?: string | null;
  stable_key?: string | null;
  metadata?: Record<string, unknown>;
}

// Seat ---------------------------------------------------------------------

export interface Seat {
  seat_id: string;
  tenant_id: string;
  vendor: string;
  leased: boolean;
  ref_count: number;
}

export interface SeatsResponse {
  seats: Seat[];
}

// Topology -----------------------------------------------------------------

export interface TopologyNode {
  [key: string]: string;
}

export interface TopologyEdge {
  [key: string]: string;
}

export interface TopologySaveRequest {
  nodes: TopologyNode[];
  edges: TopologyEdge[];
}

export interface AclRole {
  name: string;
  agents: string[];
  can_send_to: string[];
  can_receive_from: string[];
  can_dispatch_tasks: boolean;
  can_reassign_tasks: boolean;
}

export interface TopologySaveResponse {
  squad_id: string;
  effective_topology: {
    default_policy: string;
    roles: AclRole[];
  };
}

export interface TopologyGetResponse {
  squad_id: string;
  stored: unknown;
}

// FinOps -------------------------------------------------------------------

export interface ProjectRollup {
  tenant_id: string;
  project_id: string;
  total_cost_usd: string;
  token_cost_usd: string;
  seat_cost_usd: string;
  record_count: number;
}

// Tracing ------------------------------------------------------------------

export interface TraceEvent {
  event_id: string;
  trace_id: string;
  layer: string;
  signal_type: string;
  tenant_id: string;
  project_id: string;
  issue_id: string;
  agent_id: string;
  runtime_id: string;
  message: string;
  token_burn: number;
  seat_seconds: number;
  details: Record<string, unknown>;
}

// Task ---------------------------------------------------------------------

export interface TaskCreateRequest {
  task_id: string;
  tenant_id: string;
  project_id: string;
  issue_id?: string;
  assignee_runtime: string;
  prompt: string;
  credential_ref?: string;
  operation_mode: 'terminal' | 'socket';
  seat_seconds?: number;
}

export interface TaskDispatchResponse {
  task_id: string;
  operation_mode: 'terminal' | 'socket';
  events: Record<string, unknown>[];
}

// Chat ---------------------------------------------------------------------

export type ChatRole = 'system' | 'user' | 'assistant' | 'tool';

export interface ChatMessage {
  role: ChatRole;
  content: string;
}

export interface ChatCompletionRequest {
  tenant_id: string;
  project_id: string;
  runtime_id: string;
  model: string;
  messages: ChatMessage[];
  temperature?: number;
  max_tokens?: number;
  stream?: boolean;
  metadata?: Record<string, unknown>;
}

export interface ChatCompletionResponse {
  id?: string;
  model?: string;
  runtime_id?: string;
  choices?: Array<{
    message?: ChatMessage;
    finish_reason?: string;
    index?: number;
  }>;
  message?: ChatMessage;
  content?: string;
  usage?: {
    input_tokens?: number;
    output_tokens?: number;
    total_tokens?: number;
  };
  trace_id?: string;
  metadata?: Record<string, unknown>;
}

export interface Issue {
  issue_id: string;
  title: string;
  description: string | null;
  status: string;
  priority: string;
  assignee_runtime: string | null;
  operation_mode: string;
  tenant_id: string;
  project_id: string;
  due_date: string | null;
  metadata: Record<string, unknown>;
  created_at: string | null;
  updated_at: string | null;
}

export interface IssueListParams {
  scope?: "all" | "assigned" | "created" | "my-agents";
  agent_id?: string;
}

// Inbox --------------------------------------------------------------------

export type InboxEventType =
  | 'task_completed'
  | 'task_failed'
  | 'issue_created'
  | 'issue_assigned'
  | 'agent_registered'
  | 'agent_removed'
  | 'system'
  | 'info';

export interface InboxEvent {
  id: string;
  tenant_id: string;
  type: InboxEventType;
  title: string;
  message: string;
  read: boolean;
  archived: boolean;
  created_at: string | null;
}

export interface InboxListParams {
  tenantId?: string;
  read?: boolean;
  archived?: boolean;
}

export interface UnreadCountResponse {
  count: number;
}

export interface BulkArchiveResponse {
  archived_count: number;
}
