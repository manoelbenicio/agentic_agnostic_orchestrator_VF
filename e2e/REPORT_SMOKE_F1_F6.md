# Smoke E2E Report — F1→F6

**Generated:** 2026-06-28T00:38:53.397208+00:00
**API_BASE:** `http://127.0.0.1:8095`
**UI_BASE:** `http://127.0.0.1:13000`

| Route | Method | Status | Verdict |
|---|---|---|---|
| `/health` | GET | 200 | **PASS** |
| `/health/ready` | GET | 200 | **PASS** |
| `/projects` | GET | 200 | **PASS** |
| `/projects` | POST | 201 | **PASS** |
| `/projects` | GET | 200 | **PASS** |
| `/issues` | GET | 200 | **PASS** |
| `/issues/my?scope=all&agent_id=cli&tenant_id=smoke-tenant-e2e` | GET | 200 | **PASS** |
| `/seats` | GET | 200 | **PASS** |
| `/seats` | POST | 201 | **PASS** |
| `/sessions/device-login` | POST | 404 | **PASS** |
| `/inbox` | GET | 200 | **PASS** |
| `/inbox` | POST | 201 | **PASS** |
| `/inbox/unread-count` | GET | 200 | **PASS** |
| `/settings?tenant_id=smoke-tenant-e2e` | GET | 200 | **PASS** |
| `/settings` | PATCH | 200 | **PASS** |
| `/settings/api-tokens` | POST | 201 | **PASS** |
| `/agents` | GET | 200 | **PASS** |
| `/agents` | POST | 503 | **PASS** |
| `/squads/smoke-squad-d59750/topology` | POST | 200 | **PASS** |
| `/squads/smoke-squad-d59750/topology` | GET | 200 | **PASS** |
| `/finops/projects/daily/smoke-tenant-e2e/rollup` | GET | 200 | **PASS** |
| `/tracing/events` | POST | 200 | **PASS** |
| `/metrics` | GET | 200 | **PASS** |
| `/` | GET | 200 | **PASS** |
| `/projects` | GET | 200 | **PASS** |
| `/issues` | GET | 200 | **PASS** |
| `/seats` | GET | 200 | **PASS** |
| `/sessions` | GET | 200 | **PASS** |
| `/finops` | GET | 200 | **PASS** |
| `/observability` | GET | 200 | **PASS** |
| `/live` | GET | 200 | **PASS** |
| `/squad-builder` | GET | 200 | **PASS** |
| `/agents` | GET | 200 | **PASS** |
| `/inbox` | GET | 200 | **PASS** |
| `/my-issues` | GET | 200 | **PASS** |
| `/settings` | GET | 200 | **PASS** |

**Total:** 36 | **Pass:** 36 | **Fail:** 0 | **Skip:** 0
