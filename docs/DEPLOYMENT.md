# Agnostic Orchestration Platform (AOP) - Deployment Guide

This document outlines the standard operating procedures for deploying the Agnostic Orchestration Platform (AOP) across local development environments and production Kubernetes clusters.

## Prerequisites
Ensure the following dependencies are installed and configured on your target machine or CI/CD runner before proceeding:
- **Python**: `3.11+` (Strictly required for asynchronous `asyncio.TaskGroup` features and `pydantic` v2 data modeling capabilities).
- **Node.js**: `18+` (Required for building and serving the React Web Frontend).
- **Docker & Docker Compose**: `v24+` / `v2.20+` (Required for bootstrapping containerized development databases and local environments).
- **kubectl & Helm**: (Required exclusively for Production Kubernetes cluster deployments).

---

## Local Development
Local development leverages Docker Compose to instantly orchestrate the required persistence layers (PostgreSQL equipped with `pgvector` and Redis) alongside the backend applications.

1. **Environment Setup**:
   Clone the repository and copy the default environment variable template:
   ```bash
   cp .env.example .env
   ```

2. **Bootstrapping the Cluster**:
   Bring up the core backing services and backend API containers:
   ```bash
   docker-compose up -d --build
   ```
   
3. **Running the Frontend**:
   In a separate terminal, navigate to the web directory to initialize the React UI:
   ```bash
   cd web/
   npm install
   npm run dev
   ```

---

## Production Deployment
Production deployments are designed strictly for Kubernetes, natively supporting multi-pod scaling, load-balancing, and automated rolling updates safely guided by health probes.

### Kubernetes Manifests & Helm
AOP is deployed via a centralized Helm chart encapsulating Deployments, Services, Ingress routes, and ConfigMaps.

1. **Configure Helm Values**:
   Create a custom `values-prod.yaml` mapping your production resources:
   ```yaml
   replicaCount: 3
   image:
     repository: aop-control-plane
     tag: "v1.2.0"
   env:
     - name: DB_HOST
       value: "aop-prod-db-cluster.internal"
   ingress:
     enabled: true
     hosts:
       - host: aop.internal.corp
   ```

2. **Deploy via Helm**:
   ```bash
   helm upgrade --install aop-core ./charts/aop -f values-prod.yaml --namespace aop-production --create-namespace
   ```

---

## Environment Variables
The platform utilizes environment variables to maintain strict runtime environment agnosticism. 

| Variable | Description | Default / Example |
|----------|-------------|-------------------|
| `ENVIRONMENT` | Defines the current execution context (`local`, `staging`, `production`). | `local` |
| `DB_DSN` | The connection string for PostgreSQL / `asyncpg`. | `postgresql://user:pass@localhost:5432/aop` |
| `REDIS_URL` | The connection URI for the Redis caching tier. | `redis://localhost:6379/0` |
| `JWT_SECRET` | Cryptographic secret used for signing and verifying JSON Web Tokens. | *Must be overridden in prod* |
| `API_RATE_LIMIT` | Global requests-per-minute threshold for endpoints. | `60` |
| `OLLAMA_BASE_URL`| Internal routing endpoint for local LLM adapters. | `http://localhost:11434` |
| `LOG_LEVEL` | Application logging verbosity (`DEBUG`, `INFO`, `WARN`, `ERROR`). | `INFO` |

---

## Database Migrations
AOP strictly relies on Alembic to manage safe, transactional schema migrations against PostgreSQL to prevent data corruption.

1. **Generating a new Migration**:
   If you modify the SQLAlchemy ORM models, generate a new migration revision:
   ```bash
   alembic revision --autogenerate -m "Added provisioning status column"
   ```

2. **Applying Migrations**:
   Run the upgrade command to apply unapplied changes to your current database:
   ```bash
   alembic upgrade head
   ```

3. **Rolling Back**:
   Revert the last applied migration safely:
   ```bash
   alembic downgrade -1
   ```

---

## Monitoring
AOP exposes native telemetry designed to be scraped seamlessly by Prometheus and visualized via Grafana.

- **Prometheus Targets**:
  The Control Plane and AI Platform expose standard Prometheus metrics at `GET /metrics`. Configure your `prometheus.yml` scrape configs to target these endpoints on an interval of `15s`.
- **Grafana Dashboards**:
  Pre-built Grafana JSON templates are available in the `/deploy/grafana/` directory. Import these to visualize LLM routing latencies, vector-search chunking durations, active provisioning pipelines, and API rate-limiting block ratios.

---

## Troubleshooting
Common operational issues and reliable remediation paths:

1. **Database Connection Refused**:
   - *Symptom*: Pod crashes immediately with `asyncpg.exceptions.CannotConnectNowError`.
   - *Fix*: Ensure your `DB_DSN` matches the internal DNS of the cluster. Verify that `pgvector` extensions are successfully enabled on the target database, as the backend will fail to start without them.
2. **LLM Adapter Timeouts (Local Ollama)**:
   - *Symptom*: Endpoints return `504 Gateway Timeout` when routing to `localhost:11434`.
   - *Fix*: Verify the local Ollama daemon is running natively. Ensure the requested model (e.g., `llama3`) is physically downloaded using `ollama run llama3`.
3. **Kubernetes Pods Stuck in CrashLoopBackOff**:
   - *Symptom*: Deployments fail to become healthy after helm deployment.
   - *Fix*: The `GET /health/live` probe is likely failing. Check the container logs using `kubectl logs <pod-name>` to identify missing mandatory environment variables (like `JWT_SECRET`) causing startup crashes.
