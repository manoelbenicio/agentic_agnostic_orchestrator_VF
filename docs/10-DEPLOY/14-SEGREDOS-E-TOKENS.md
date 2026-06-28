# 14 — Segredos e Tokens

## 1. Token do HerdMaster (segredo central do acoplamento)

O acoplamento AOP ↔ HerdMaster usa um **Bearer token** gerado e gerenciado por `ops/common.sh`.

### Geração (`ensure_herdmaster_token`)

```bash
HERDMASTER_TOKEN_FILE="${RUNTIME_DIR}/herdmaster.token"   # /tmp/aop-ops-runtime/herdmaster.token
ensure_herdmaster_token() {
  if [[ ! -f "${HERDMASTER_TOKEN_FILE}" ]]; then
    umask 077
    if command -v openssl >/dev/null 2>&1; then
      openssl rand -hex 24 > "${HERDMASTER_TOKEN_FILE}"
    else
      date +%s%N | sha256sum | awk '{print $1}' > "${HERDMASTER_TOKEN_FILE}"
    fi
  fi
  chmod 600 "${HERDMASTER_TOKEN_FILE}" 2>/dev/null || true
}
```

- **Local:** `/tmp/aop-ops-runtime/herdmaster.token`
- **Permissão:** `600` (apenas o dono lê) — token canônico.
- **Geração:** `openssl rand -hex 24` (48 hex chars); fallback `sha256sum` de timestamp.
- **Idempotente:** só gera se não existir. Para **rotacionar**, apague o arquivo e reinicie (`stop.sh` + `start.sh`).

---

## 2. Cópia legível para o Prometheus (644)

O Prometheus roda como `nobody` dentro do container e **não** consegue ler o token `600`. Por isso `common.sh` mantém uma cópia sincronizada `644`:

```bash
PROM_TOKEN_FILE="${RUNTIME_DIR}/prometheus.token"
write_prometheus_token() {
  ensure_herdmaster_token
  printf '%s' "$(herdmaster_token)" > "${PROM_TOKEN_FILE}"   # sem newline final
  chmod 644 "${PROM_TOKEN_FILE}" 2>/dev/null || true
}
```

- **Local:** `/tmp/aop-ops-runtime/prometheus.token`
- **Permissão:** `644` (legível pelo container via bind-mount, para `credentials_file`).
- **Sem newline final** (evita corromper o header `Authorization`).
- Escrito por `start.sh` **antes** de subir a observabilidade (`write_prometheus_token`).

> Compromisso de segurança consciente: o token fica `644` para o Prometheus autenticar no `/metrics` do HerdMaster. Confinar via permissões de FS do host e bind `127.0.0.1`.

---

## 3. Config TOML do HerdMaster (contém o token)

`write_herdmaster_config` gera `/tmp/aop-ops-runtime/herdmaster.config.toml` (`600`), incluindo o token em `[api].token`, a `DATABASE_URL` em `[database].url`, e o ACL padrão:

```toml
[acl]
default_policy = "deny"

[[acl.roles]]
name = "orchestrator"
agents = ["cli"]
can_send_to = ["*"]
can_receive_from = ["*"]
can_dispatch_tasks = true
can_reassign_tasks = true

[[acl.roles]]
name = "worker"
agents = ["*"]
can_send_to = ["cli"]
can_receive_from = ["cli"]
can_dispatch_tasks = false
can_reassign_tasks = false

[api]
bind = "127.0.0.1"
port = 8080
token = "<token>"
```

- Escrito de forma **atômica** (`mktemp` + `mv`), permissão `600`.
- O ACL `default_policy = "deny"` é a base da segurança de topologia: workers só falam com o `cli` (TL); comunicação lateral é negada. Provado no E2E ([`40-VERIFICACAO/41-SMOKE-E2E.md`](../40-VERIFICACAO/41-SMOKE-E2E.md)).

---

## 4. Como o token é consumido

| Consumidor | Mecanismo |
|-----------|-----------|
| `curl` de healthcheck (`common.sh`) | header `Authorization: Bearer <token>` via `herdmaster_auth_header` |
| Control-plane (`start.sh`) | env `HERDMASTER_TOKEN` injetada no uvicorn |
| Coupling probe (`_coupling_health`) | `herdmaster_authenticated_probe(url, token=...)` |
| Prometheus | `credentials_file` apontando para `prometheus.token` |

### Verificação

```bash
# Token existe e está 600?
stat -c '%a %n' /tmp/aop-ops-runtime/herdmaster.token 2>/dev/null
# Cópia do Prometheus está 644 e sem newline?
stat -c '%a %n' /tmp/aop-ops-runtime/prometheus.token 2>/dev/null
# HerdMaster aceita o token?
curl -s -o /dev/null -w '%{http_code}\n' \
  -H "Authorization: Bearer $(tr -d '\r\n' < /tmp/aop-ops-runtime/herdmaster.token)" \
  http://127.0.0.1:8080/metrics
```

---

## 5. Boas práticas de segredos (recomendação)

- **Nunca** commitar `deploy/.env` nem os arquivos de `/tmp/aop-ops-runtime/`.
- Em produção, mover o `RUNTIME_DIR` para fora de `/tmp` (volátil e world-traversável) via `AOP_OPS_RUNTIME_DIR`.
- Rotacionar o token HerdMaster periodicamente (apagar `herdmaster.token` + restart).
- O `requirepass` já está aplicado no Redis para proteger acesso via loopback.
