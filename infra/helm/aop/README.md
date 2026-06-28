# AOP Helm Chart

Production Helm chart for the **AOP (Agent Orchestration Platform)** — a multi-tenant SaaS agent orchestration platform.

Deploys all AOP services to Kubernetes:
- **controlPlane** — FastAPI/uvicorn control plane (:8090)
- **web** — Next.js frontend (:13000)
- **nginx** — reverse proxy / load balancer (:8000)
- **postgres** — pgvector Postgres 17 (:5432)
- **redis** — Redis Stack Server (:6379)
- **herdmaster** — sibling control plane (:8080)

## Install

```bash
# Create namespace
kubectl create namespace aop

# Install the chart
helm install aop infra/helm/aop/ -n aop -f my-values.yaml
```

## Configuration

Key values (override in `my-values.yaml`):

| Key | Description | Default |
|-----|-------------|---------|
| `namespace` | Target namespace | `aop` |
| `secrets.useExternalSecrets` | Use External Secrets Operator | `true` |
| `secrets.backend` | Secret backend (`aws-secrets-manager`) | `aws-secrets-manager` |
| `ingress.enabled` | Enable Ingress | `true` |
| `ingress.className` | Ingress class | `nginx` |
| `controlPlane.replicaCount` | Control-plane replicas | `2` |
| `controlPlane.hpa.enabled` | Enable Horizontal Pod Autoscaler | `true` |
| `controlPlane.pdb.enabled` | Enable Pod Disruption Budget | `true` |
| `postgres.persistence.size` | Postgres volume size | `20Gi` |
| `postgres.replication.enabled` | Enable logical replication (Phase 3) | `false` |
| `redis.ha.mode` | Redis HA mode (`standalone\|sentinel\|cluster`) | `standalone` |
| `herdmaster.enabled` | Deploy HerdMaster sibling | `true` |

## Prerequisites

- Kubernetes 1.27+
- Helm 3.12+
- External Secrets Operator (if `secrets.useExternalSecrets=true`)
- NGINX Ingress Controller (if `ingress.enabled=true`)
- StorageClass for persistence (Postgres/Redis)

## Verification

```bash
helm lint infra/helm/aop/
helm template infra/helm/aop/ | less
helm install aop infra/helm/aop/ -n aop --dry-run --debug
```

See `docs/10-DEPLOY/18-K8S-MULTI-REGIAO.md` for the full multi-region architecture.
