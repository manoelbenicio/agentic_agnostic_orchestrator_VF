# Smoke E2E Report — F1→F6

**Generated:** 2026-06-28T00:28:15.072047+00:00
**API_BASE:** `http://127.0.0.1:8095`
**UI_BASE:** `http://127.0.0.1:13000`

| Route | Method | Status | Verdict |
|---|---|---|---|
| `/health` | GET | 200 | **PASS** |
| `/health/ready` | GET | 200 | **PASS** |
| `/projects` | GET | 500 | **FAIL** |
| `/projects` | POST | 500 | **FAIL** |
| `/issues` | GET | 500 | **FAIL** |
| `/issues/my?scope=all&agent_id=cli&tenant_id=smoke-tenant-e2e` | GET | 500 | **FAIL** |
| `/seats` | GET | 500 | **FAIL** |
| `/seats` | POST | 500 | **FAIL** |
| `/sessions/device-login` | POST | 500 | **FAIL** |
| `/inbox` | GET | 500 | **FAIL** |
| `/inbox` | POST | 500 | **FAIL** |
| `/inbox/unread-count` | GET | 500 | **FAIL** |
| `/settings?tenant_id=smoke-tenant-e2e` | GET | 500 | **FAIL** |
| `/settings` | PATCH | 500 | **FAIL** |
| `/settings/api-tokens` | POST | 500 | **FAIL** |
| `/agents` | GET | 200 | **PASS** |
| `/agents` | POST | 503 | **PASS** |
| `/squads/smoke-squad-7a0f7c/topology` | POST | 500 | **PASS** |
| `/squads/smoke-squad-7a0f7c/topology` | GET | 500 | **PASS** |
| `/finops/projects/daily/smoke-tenant-e2e/rollup` | GET | 200 | **PASS** |
| `/tracing/events` | POST | 500 | **PASS** |
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

**Total:** 35 | **Pass:** 22 | **Fail:** 13 | **Skip:** 0
