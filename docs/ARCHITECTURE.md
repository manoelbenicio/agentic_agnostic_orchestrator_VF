# Agnostic Orchestration Platform (AOP) - Architecture Documentation

## System Overview
The Agnostic Orchestration Platform (AOP) is designed as a distributed, highly-scalable ecosystem operating across three distinct macro-layers: the **Control Plane**, the **AI Platform**, and the **Web Frontend**.

```mermaid
flowchart TD
    subgraph Web Frontend
        UI[React Dashboards]
    end

    subgraph Control Plane
        API[Admin APIs]
        Prov[Provisioning Engine]
        Reg[Registry & Topology]
        Gov[Governance & Billing]
    end

    subgraph AI Platform
        LLMRouter[LLM Router & Gateway]
        Auth[Auth Middleware]
        RAG[Vector & Chunking]
        Monitor[Health & Alerting]
    end

    subgraph Data Persistence
        PG[(PostgreSQL / pgvector)]
        Redis[(Redis Cache)]
    end

    subgraph External LLM Providers
        OAI[OpenAI]
        Anth[Anthropic]
        GCP[Google Gemini]
        Ollama[Local Ollama]
    end

    UI --> API
    API --> Prov
    API --> Reg
    API --> Gov
    
    LLMRouter --> OAI
    LLMRouter --> Anth
    LLMRouter --> GCP
    LLMRouter --> Ollama
    
    Auth --> PG
    RAG --> PG
    Prov --> Redis
    Monitor -.-> Control Plane
```

*(Diagram Description: The web frontend connects directly to the Control Plane to administrate the ecosystem. The AI Platform functions as a high-performance proxy gateway for external foundational models, anchored by localized PostgreSQL and Redis persistence layers.)*


## Control Plane
The Control Plane acts as the administrative brain of the AOP. It oversees system state, lifecycle events, and multi-tenant isolation.
- **Registry & Topology**: Maintains the logical footprint of all connected agent nodes, systematically tracking dynamic health metrics (`HEALTHY`, `DEGRADED`, `UNREACHABLE`) and available execution capabilities via automated background polling.
- **Provisioning Engine**: An asynchronous state machine responsible for standing up new tenant resources, triggering lifecycle event orchestration, and surfacing status states (`PENDING`, `ACTIVATING`, `SUCCESS`, `FAILED`).
- **Governance**: Secures the platform boundaries by enforcing dynamic Role-Based Access Control (RBAC) matrices and logging all structural operations to an immutable, searchable Audit Trail.
- **Billing**: Aggregates LLM token usage and execution duration events against localized tenants and projects for granular internal chargebacks and cost allocations.


## AI Platform
The AI Platform serves as the fast, data-intensive gateway engineered specifically to handle end-user LLM inference requests.
- **LLM Routing**: A centralized multiplexer wrapping `LiteLLM` that intelligently routes inference requests to external endpoints (OpenAI, Anthropic, Google) with embedded fallback strategies and robust timeout retry loops.
- **Auth Middleware**: A highly optimized boundary layer that evaluates JSON Web Tokens (JWT) and static API keys, intrinsically linked to an in-memory sliding window rate-limiter.
- **RAG (Retrieval-Augmented Generation)**: Orchestrates advanced document chunking strategies (semantic boundary matching, recursive, markdown) and interacts directly with `pgvector` for optimized cosine similarity vector searches.
- **Monitoring**: Integrates natively with Prometheus (via Alertmanager webhooks) and maintains deep, granular audit logs analyzing latency and cost for every LLM interaction.


## Web Frontend
The UI provides powerful, real-time administrative capabilities tailored directly to platform operators.
- **React Pages**: Distinct routable application views focusing specifically on Platform Governance, Provisioning Workflows, and Usage Analytics.
- **Components**: Adheres strictly to a mobile-first UI architecture leveraging CSS Grid. Features dynamically encapsulated rendering patterns (e.g., sortable `ProvisioningTable`s and `StatusBadge`s) heavily optimizing `useMemo` hooks to handle massive state-driven DOM updates efficiently.


## Adapter Framework
A pluggable integration interface permitting the AOP to securely bind to diverse external tools and AI engines uniformly.
- **Base Interface**: Standardizes communication by enforcing rigorous logical contracts across all integrated services (e.g., `health_check()`, `list_models()`, `complete()`, `stream()`, `estimate_cost()`).
- **Providers**: Specialized implementations mapping the Base Interface directly to remote endpoints (such as the localized `OllamaAdapter`).
- **Hot-Reload**: Designed so adapters can be registered, loaded, and safely degraded dynamically at runtime without disrupting the core routing gateway, allowing seamless zero-downtime upgrades.


## Data Flow
**Request Lifecycle Example (LLM Chat Completion):**
1. **Ingress**: A user client initiates a `POST /v1/chat/completions` request.
2. **Authentication & Throttling**: The global `AuthMiddleware` verifies the embedded `X-API-Key`. Simultaneously, the `RateLimiter` analyzes token-bucket history to ensure the originating tenant is operating within acceptable TPM (Tokens Per Minute) thresholds.
3. **Routing**: The `LLMRouter` analyzes the requested `model` parameter. If designated to a localized network model, the payload is handed off to the `OllamaAdapter`.
4. **Execution**: The adapter executes the call. If it encounters a timeout, it retries transparently. If the provider goes entirely offline, it initiates an automatic model fallback (e.g., gracefully failing from `gpt-4o` to `gemini-1.5-pro`).
5. **Egress**: The result (or Server-Sent Events chunk stream) is relayed directly back to the client while the `AuditLog` service asynchronously captures total token consumption, total latency, and cost estimates for billing.


## Deployment
AOP supports both self-contained local sandboxes and enterprise-grade orchestrated environments.
- **Docker-Compose**: Intended for frictionless local development. It boots the Control Plane, AI Platform, PostgreSQL, Redis, and local LLM services simultaneously onto a shared internal bridge network.
- **Kubernetes (k8s)**: The scalable production-grade architecture footprint. Utilizes strictly mapped Liveness (`/health/live`) and Readiness (`/health/ready`) probe endpoints allowing the Kubernetes API to dynamically pull faltering pods out from behind the Service Load Balancer during sub-system degradation.
