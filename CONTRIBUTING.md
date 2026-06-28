# Contributing to the Agnostic Orchestration Platform (AOP)

Welcome to the **AOP** engineering ecosystem! We maintain a high-performance multi-tenant AI control plane designed for extreme scale and architectural rigidity. This document outlines the explicit constraints, logic, and operational pipelines required to submit changes securely to the monolithic platform.

---

## 🚀 Getting Started

Before writing any code, ensure you have the required strict operational toolchains installed natively on your host:
- **Docker & Docker Compose**
- **Python 3.11+**
- **Node.js 18+** (For Frontend UI compilation logic)
- **Poetry** (For explicit backend dependency locking)

---

## 🛠️ Dev Setup

Our entire monolithic stack is geometrically mapped to boot seamlessly across a unified containerized TCP network utilizing `docker-compose`.

1. **Initialize the Cluster**:
   ```bash
   docker-compose up --build -d
   ```
2. **Execute Database Migrations** (Executes strictly inside the control-plane container):
   ```bash
   docker-compose exec control-plane poetry run migrate
   ```
3. **Access Topologies**:
   - FastAPI Control Plane Gateway: `http://localhost:8000`
   - React UI Dashboard: `http://localhost:3000`
   - Swagger OpenAPI Docs: `http://localhost:8000/docs`

---

## 🎨 Code Style

Consistency across the codebase is non-negotiable and enforced rigorously at the CI level.

**Python (Backend)**
We enforce strict AST formatting and linting natively utilizing **Ruff**:
```bash
# Execute local lint checks and formatting
poetry run ruff check . --fix
poetry run ruff format .
```
- **Type Hinting**: All functions, variables, and arrays MUST utilize modern Python type hinting. The CI enforces strict validations natively executing `mypy`.

**TypeScript/React (Frontend)**
We rely on **Prettier** for exact geometric formatting bounds:
```bash
npm run format
```
- Absolutely no `any` types. Rely exclusively on strict Interface and Type definitions.

---

## 🌿 Branch Naming

All branching logic must explicitly follow this precise convention to trigger our CI execution matrices natively:
- `feature/<ticket>-<description>` (e.g., `feature/AOP-104-llm-router-fallback`)
- `fix/<ticket>-<description>` (e.g., `fix/AOP-209-pgvector-index-crash`)
- `docs/<description>` (e.g., `docs/update-api-schemas`)

---

## 📝 Conventional Commits

We leverage highly automated semantic release pipelines. Your commit messages MUST follow the **Conventional Commits** schema natively to execute versioning bounds properly:
- `feat: integrate Anthropic Claude 3.5 Sonnet`
- `fix(auth): trap null pointer in API key rotation logic`
- `refactor(billing): optimize PostgreSQL date_trunc aggregation queries`
- `docs: update deployment architecture documentation`

---

## 🛡️ Testing Requirements

Pull requests will automatically fail CI bounds if test coverage drops or assertions panic.
- **Backend Logic**: You must write explicit `pytest` fixtures for all new control plane routers. If mapping async integrations, tests must be wrapped natively utilizing `pytest-asyncio`.
- **Frontend Logic**: Components must be tested via React Testing Library asserting exact geometric DOM states cleanly.

Run execution checks locally before submitting:
```bash
poetry run pytest tests/
```

---

## 🔄 PR Process

1. Isolate your feature strictly inside a branch off `main`.
2. Push your logical branch and open a Pull Request.
3. The PR Title must natively match the Conventional Commit logic (e.g., `feat(rag): construct HTML ingestion parser mapping`).
4. Ensure all CI hooks (Ruff, Mypy, Pytest) execute flawlessly.
5. Request an architectural code review from at least **1 Core Maintainer**.

---

## 🏗️ Architecture Overview

When contributing, absolutely respect the fundamental architectural boundaries mapping the project:
- **`agnostic-ai-platform/`**: Handles decoupled AI operations. This module executes pure mathematical logic like RAG Document parsing, heavy NLP Entity chunking, and massive LLM network Proxy routing algorithms.
- **`control-plane/`**: Handles Platform Governance. This means User Identities, Tenant boundary definitions, complex Financial Billing arrays, and PostgreSQL Connections natively live here.
- **`web/`**: The React UI. Operates completely stateless, relying natively on the FastAPI API Gateway for all structural DOM mutations.

_By submitting a Pull Request, you explicitly agree to license your code cleanly under the MIT License constraints dictating this project._
