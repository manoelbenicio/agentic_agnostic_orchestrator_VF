// ---------------------------------------------------------------------------
// AOP Control-Plane – Typed Fetch API Client
// ---------------------------------------------------------------------------

import type {
  HealthResponse,
  ReadyResponse,
  Agent,
  AgentCreateRequest,
  SeatsResponse,
  TopologySaveRequest,
  TopologySaveResponse,
  TopologyGetResponse,
  ProjectRollup,
  TraceEvent,
  TaskCreateRequest,
  TaskDispatchResponse,
  ChatCompletionRequest,
  ChatCompletionResponse,
  ChatMessage,
  InboxEvent,
  InboxListParams,
  UnreadCountResponse,
  BulkArchiveResponse,
  Issue,
  IssueListParams,
} from './api-types';

// ---------------------------------------------------------------------------
// Custom Error
// ---------------------------------------------------------------------------

export class ApiError extends Error {
  public readonly status: number;
  public readonly statusText: string;
  public readonly body: unknown;

  constructor(status: number, statusText: string, body: unknown) {
    const message =
      typeof body === 'object' && body !== null && 'detail' in body
        ? String((body as Record<string, unknown>).detail)
        : `API error ${status}: ${statusText}`;
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.statusText = statusText;
    this.body = body;
  }
}

// ---------------------------------------------------------------------------
// Client
// ---------------------------------------------------------------------------

export class ApiClient {
  private readonly baseUrl: string;
  private readonly cache = new Map<string, { data: unknown; expires: number }>();
  private readonly defaultCacheTtl = 5000;

  constructor(baseUrl?: string) {
    this.baseUrl =
      baseUrl ??
      (typeof process !== 'undefined'
        ? process.env.NEXT_PUBLIC_API_URL ?? 'http://127.0.0.1:8090'
        : 'http://127.0.0.1:8090');
  }

  // ---- internal helpers ---------------------------------------------------

  private async request<T>(
    method: string,
    path: string,
    body?: unknown,
  ): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    const cacheKey = `${method}:${url}`;

    if (method === 'GET') {
      const cached = this.cache.get(cacheKey);
      if (cached && Date.now() < cached.expires) {
        return cached.data as T;
      }
    }

    const headers: Record<string, string> = {
      Accept: 'application/json',
    };

    if (body !== undefined) {
      headers['Content-Type'] = 'application/json';
    }

    const res = await fetch(url, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });

    // For 204 No Content (e.g. DELETE), return an empty object.
    if (res.status === 204) {
      return {} as T;
    }

    let parsed: unknown;
    const contentType = res.headers.get('content-type') ?? '';
    if (contentType.includes('application/json')) {
      parsed = await res.json();
    } else {
      parsed = await res.text();
    }

    if (!res.ok) {
      throw new ApiError(res.status, res.statusText, parsed);
    }

    if (method === 'GET') {
      this.cache.set(cacheKey, { data: parsed, expires: Date.now() + this.defaultCacheTtl });
    }

    return parsed as T;
  }

  private get<T>(path: string): Promise<T> {
    return this.request<T>('GET', path);
  }

  private post<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>('POST', path, body);
  }

  private del<T>(path: string): Promise<T> {
    return this.request<T>('DELETE', path);
  }

  // ---- Health -------------------------------------------------------------

  async health(): Promise<HealthResponse> {
    return this.get<HealthResponse>('/health');
  }

  async ready(): Promise<ReadyResponse> {
    return this.get<ReadyResponse>('/health/ready');
  }

  // ---- Agents -------------------------------------------------------------

  async listAgents(): Promise<Agent[]> {
    return this.get<Agent[]>('/agents');
  }

  async createAgent(req: AgentCreateRequest): Promise<Agent> {
    return this.post<Agent>('/agents', req);
  }

  async deleteAgent(agentId: string): Promise<void> {
    await this.del<void>(`/agents/${encodeURIComponent(agentId)}`);
  }

  // ---- Seats --------------------------------------------------------------

  async getSeats(): Promise<SeatsResponse> {
    return this.get<SeatsResponse>('/seats');
  }

  // ---- Topology -----------------------------------------------------------

  async saveTopology(
    squadId: string,
    req: TopologySaveRequest,
  ): Promise<TopologySaveResponse> {
    return this.post<TopologySaveResponse>(
      `/squads/${encodeURIComponent(squadId)}/topology`,
      req,
    );
  }

  async getTopology(squadId: string): Promise<TopologyGetResponse> {
    return this.get<TopologyGetResponse>(
      `/squads/${encodeURIComponent(squadId)}/topology`,
    );
  }

  // ---- FinOps -------------------------------------------------------------

  async projectRollup(
    tenantId: string,
    projectId: string,
  ): Promise<ProjectRollup> {
    return this.get<ProjectRollup>(
      `/finops/projects/${encodeURIComponent(tenantId)}/${encodeURIComponent(projectId)}/rollup`,
    );
  }

  // ---- Tracing ------------------------------------------------------------

  async traceAgent(agentId: string): Promise<TraceEvent[]> {
    return this.get<TraceEvent[]>(
      `/tracing/agents/${encodeURIComponent(agentId)}`,
    );
  }

  async traceRuntime(runtimeId: string): Promise<TraceEvent[]> {
    return this.get<TraceEvent[]>(
      `/tracing/runtimes/${encodeURIComponent(runtimeId)}`,
    );
  }

  // ---- Tasks --------------------------------------------------------------

  async listTasks(): Promise<any> {
    return this.get<any>('/tasks');
  }

  async createTask(req: TaskCreateRequest): Promise<TaskDispatchResponse> {
    return this.post<TaskDispatchResponse>('/tasks', req);
  }

  // ---- Chat ---------------------------------------------------------------

  async chatCompletion(req: ChatCompletionRequest): Promise<ChatCompletionResponse> {
    const payload = {
      model: req.model,
      messages: req.messages,
      temperature: req.temperature,
      max_tokens: req.max_tokens,
      stream: req.stream,
      metadata: {
        ...(req.metadata ?? {}),
        tenant_id: req.tenant_id,
        project_id: req.project_id,
        runtime_id: req.runtime_id,
      },
    };
    try {
      return await this.post<ChatCompletionResponse>('/llm/chat/completions', payload);
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        try {
          return await this.post<ChatCompletionResponse>('/api/llm/chat/completions', payload);
        } catch (aliasError) {
          if (aliasError instanceof ApiError && aliasError.status === 404) {
            return this.post<ChatCompletionResponse>('/api/v1/llm-proxy/chat/completions', payload);
          }
          throw aliasError;
        }
      }
      throw error;
    }
  }

  // ---- Issues -------------------------------------------------------------

  async listIssues(): Promise<Issue[]> {
    return this.get<Issue[]>('/issues');
  }

  async listMyIssues(params: IssueListParams = {}): Promise<Issue[]> {
    const search = new URLSearchParams();
    if (params.scope) search.set('scope', params.scope);
    if (params.agent_id) search.set('agent_id', params.agent_id);
    const query = search.toString();
    const headers = params.agent_id ? { 'X-Agent-Id': params.agent_id } : undefined;
    
    const url = `${this.baseUrl}/issues/my${query ? `?${query}` : ''}`;
    const cacheKey = `GET:${url}`;
    
    const cached = this.cache.get(cacheKey);
    if (cached && Date.now() < cached.expires) {
      return cached.data as Issue[];
    }
    
    const res = await fetch(url, {
      method: 'GET',
      headers: {
        Accept: 'application/json',
        ...headers,
      },
    });
    if (!res.ok) {
      throw new ApiError(res.status, res.statusText, await res.text());
    }
    const data = await res.json() as Issue[];
    this.cache.set(cacheKey, { data, expires: Date.now() + this.defaultCacheTtl });
    return data;
  }

  // ---- Inbox --------------------------------------------------------------

  async listInbox(params: InboxListParams = {}): Promise<InboxEvent[]> {
    const search = new URLSearchParams();
    if (params.tenantId) search.set('tenant_id', params.tenantId);
    if (params.read !== undefined) search.set('read', String(params.read));
    if (params.archived !== undefined) search.set('archived', String(params.archived));
    const query = search.toString();
    return this.get<InboxEvent[]>(`/inbox${query ? `?${query}` : ''}`);
  }

  async unreadInboxCount(tenantId?: string): Promise<UnreadCountResponse> {
    const search = new URLSearchParams();
    if (tenantId) search.set('tenant_id', tenantId);
    const query = search.toString();
    return this.get<UnreadCountResponse>(`/inbox/unread-count${query ? `?${query}` : ''}`);
  }

  async markInboxRead(eventId: string): Promise<InboxEvent> {
    return this.post<InboxEvent>(`/inbox/${encodeURIComponent(eventId)}/read`);
  }

  async archiveInboxEvents(eventIds: string[]): Promise<BulkArchiveResponse> {
    return this.post<BulkArchiveResponse>('/inbox/bulk-archive', {
      event_ids: eventIds,
    });
  }
}

// ---------------------------------------------------------------------------
// Singleton
// ---------------------------------------------------------------------------

export const api = new ApiClient();

export function traceAgentWebSocketUrl(agentId: string) {
  const wsUrl = api['baseUrl'].replace(/^http/, "ws");
  return `${wsUrl}/ws/tracing/agents/${encodeURIComponent(agentId)}`;
}
