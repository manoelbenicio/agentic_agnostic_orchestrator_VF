#!/usr/bin/env bash
# =============================================================================
#  HerdMaster OPS Bootstrap
#  Arquivo: ops/bootstrap.sh
#  Projeto: Multi_Orchestration_Project_Tasks
#
#  USO:
#    bash bootstrap.sh <acao>
#
#  ACOES DISPONÍVEIS:
#    start         → Inicializa o HerdMaster (primeira vez ou após stop limpo)
#    stop          → Para o HerdMaster de forma ordenada
#    restart       → Para + Reinicia SEM apagar dados
#    reset-soft    → Para + Limpa tasks/prompts residuais + Reinicia (mantém DB)
#    reset-hard    → Para + Apaga DB completo + Reinicia do zero (IRREVERSÍVEL)
#    status        → Mostra estado atual de todos os componentes
#    agents-flush  → Envia /chat new para todos os panes dos agentes
#
#  FONTE DOS COMANDOS: código-fonte real lido em
#    /home/dataops-lab/.local/share/pipx/venvs/herdmaster/lib/python3.12/
#    site-packages/herdmaster/cli.py (verificado em 2026-06-25)
#
#  NUNCA executar sem autorização explícita do operador.
# =============================================================================

set -euo pipefail

# ─── Configuração ─────────────────────────────────────────────────────────────
HM_BIN="/home/dataops-lab/.local/bin/herdmaster"
HERDR_BIN="/home/dataops-lab/.local/bin/herdr"
HM_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HM_PYTHON="${HM_ROOT}/.venv/bin/python"
if ! [ -x "$HM_PYTHON" ]; then
    HM_PYTHON="python3"
fi
HM_PG_SCHEMA="${HERDMASTER_DB_SCHEMA:-hm_main}"
HM_PG_URL="${DATABASE_URL:-postgresql://aop_dev:aop_dev_postgres_20260626@127.0.0.1:5432/aop}"
HM_CONFIG_DIR="/home/dataops-lab/.config/herdmaster"
HM_PID_FILE="$HM_CONFIG_DIR/herdmaster.pid"
HM_DB="$HM_CONFIG_DIR/herdmaster.db"
HM_DB_WAL="$HM_CONFIG_DIR/herdmaster.db-wal"
HM_DB_SHM="$HM_CONFIG_DIR/herdmaster.db-shm"
HM_SOCK="$HM_CONFIG_DIR/herdmaster.sock"
HM_API_SOCK="$HM_CONFIG_DIR/herdmaster-api.sock"
HM_PROMPTS_DIR="$HM_CONFIG_DIR/prompts"

# Mapeamento pane → nome real do agente: carregado DINAMICAMENTE do roster vivo
# do herdr em runtime (nada hardcoded). Espelha exatamente `herdr pane list`.
declare -A AGENT_MAP=()
declare -A AGENT_TYPE=()
load_agent_map() {
    AGENT_MAP=(); AGENT_TYPE=()
    local json
    json="$("$HERDR_BIN" pane list 2>/dev/null)" || { warn "herdr pane list falhou; AGENT_MAP vazio"; return 1; }
    while IFS='|' read -r pid label typ; do
        [ -n "$pid" ] && { AGENT_MAP["$pid"]="$label"; AGENT_TYPE["$pid"]="$typ"; }
    done < <(printf '%s' "$json" | python3 -c "
import sys, json
for p in json.load(sys.stdin).get('result', {}).get('panes', []):
    print(p['pane_id'] + '|' + (p.get('label') or p['pane_id']) + '|' + (p.get('agent') or 'unknown'))
" 2>/dev/null)
}
# Comando de reset de contexto por tipo de CLI (cada agente usa o seu).
# Fonte: HERDR_SOCKET_API_OFICIAL — `herdr pane run` envia texto + Enter (submete).
# NOTA: a escolha /new vs /chat new é comportamento OBSERVADO de cada CLI
# (Codex vs Claude/AGY/Kiro), não documentado na API do Herdr.
reset_cmd_for_type() {
    case "$1" in
        codex) echo "/new" ;;          # OpenAI Codex CLI
        *)     echo "/chat new" ;;     # kiro / antigravity(claude/gemini) e default
    esac
}

# Lê o rodapé do pane como uma linha única (para log e verificação).
pane_tail() {
    "$HERDR_BIN" pane read "$1" --source visible --lines "${2:-3}" --format text 2>/dev/null \
        | tr '\n' ' ' | sed 's/  */ /g'
}

# Heurística de verificação: o reset "pegou" se o comando enviado NÃO continua
# parado no prompt. Tokens de tecla são MINÚSCULOS (doc oficial herdr 0.7.0).
pane_reset_landed() {
    local pane="$1" cmd="$2" tail_txt
    tail_txt="$(pane_tail "$pane" 3)"
    # Se o texto do comando ainda aparece no rodapé, o submit não ocorreu.
    case "$tail_txt" in
        *"$cmd"*) return 1 ;;   # comando ainda parado → não pegou
        *)        return 0 ;;   # prompt limpo → pegou
    esac
}

# Verificação PRIMÁRIA via `herdr agent explain --json` (fonte: doc oficial).
# Para a nossa frota (Codex/Claude/AGY/Kiro = todos screen-manifest, SEM hooks
# de lifecycle), o sinal correto não é "está idle?" e sim "está idle por uma
# REGRA QUE DEU MATCH, ou caiu no fallback default_known_agent_idle_fallback?".
# Esse fallback = Herdr não reconheceu a tela (ex.: palette do Codex aberto) e
# CHUTOU idle. Tratamos isso como NÃO-limpo — EXCETO para tipos sem regra de
# idle no manifesto (agy/kiro), onde o fallback é o melhor sinal disponível
# (Opção A: tolerância por tipo). Confirmado empiricamente em 2026-06-26:
#   codex → idle|osc_title_idle (regra)         → confiável
#   agy/kiro → idle|default_known_agent_idle_fallback → único sinal possível
# O fix durável p/ agy/kiro é um override de manifesto (não há integração).
#
# Args: $1=pane  $2=agent_type
# Imprime: "<estado>|<rule_ou_fallback_reason>"
# Retorno: 0 = limpo/confiável ; 1 = suspeito ; 2 = blocked (atenção)
pane_explain_state() {
    local pane="$1" atype="${2:-unknown}"
    "$HERDR_BIN" agent explain "$pane" --json 2>/dev/null | TOLERATE_FALLBACK_TYPE="$atype" python3 -c "
import sys, json, os
atype = os.environ.get('TOLERATE_FALLBACK_TYPE', 'unknown')
# Tipos sem regra de idle conhecida no manifesto → fallback-idle é aceitável.
# Labels REAIS do roster vivo (herdr pane list): agy (=Antigravity/Google/Gemini)
# e kiro (=AWS). Codex tem regra própria, então NÃO entra aqui.
TOLERATE = {'agy', 'kiro'}
try:
    d = json.load(sys.stdin)
except Exception:
    print('unknown|no_explain_json'); sys.exit(3)
# Chaves reais do 'agent explain --json' (verificadas em herdr 0.7.0):
#   state -> str ; matched_rule -> obj {id,state,...} | null ; fallback_reason -> str | null
state = d.get('state') or 'unknown'
mr = d.get('matched_rule') or {}
matched = mr.get('id') if isinstance(mr, dict) else None
fb = d.get('fallback_reason')
detail = matched if matched else (fb if fb else 'none')
print(state + '|' + str(detail))
# veredito de confiabilidade
if state == 'done':
    sys.exit(0)
if state == 'blocked':
    sys.exit(2)   # reconhecidamente preso → precisa de atenção/recovery
if state == 'idle' and matched and not fb:
    sys.exit(0)   # idle por regra que deu match → confiável
if state == 'idle' and fb and atype in TOLERATE:
    sys.exit(0)   # fallback-idle tolerado p/ agente sem regra de idle
sys.exit(1)       # idle-fallback (tipo com regra), working residual, ou unknown → suspeito
"
}

# Sequência de recuperação para panes presos (ex.: Codex com palette `/` aberto
# engolindo o Enter). ctrl+u limpa a linha → esc fecha o palette → re-despacha.
# Tokens minúsculos conforme HERDR_SOCKET_API_OFICIAL.
recover_stuck_pane() {
    local pane="$1" cmd="$2"
    warn "  [recover] pane=$pane preso → ctrl+u + esc + re-run \"$cmd\""
    "$HERDR_BIN" pane send-keys "$pane" ctrl+u 2>/dev/null; sleep 0.3
    "$HERDR_BIN" pane send-keys "$pane" esc     2>/dev/null; sleep 0.3
    "$HERDR_BIN" pane send-keys "$pane" ctrl+u  2>/dev/null; sleep 0.3
    "$HERDR_BIN" pane run "$pane" "$cmd"        2>/dev/null; sleep 2
}

# Bloqueia até o agente assentar em idle/done.
# IMPLEMENTAÇÃO: poll de `agent explain` (NÃO `wait agent-status --status idle`).
# MOTIVO (testado live 2026-06-26): `wait agent-status --status idle` é
# EDGE-triggered e NÃO dispara de forma confiável p/ a transição idle dos
# agentes screen-manifest (agy/kiro) — chegou a dar timeout mesmo sobre uma
# transição working->idle comprovada. Já `agent explain` rastreia o estado de
# forma precisa e instantânea. Usamos `wait agent-status --status working` em
# outros lugares (esse SIM funciona p/ transições), mas p/ "assentar em idle"
# o poll é o primitivo confiável.
# Retorno: 0 assim que idle/done; 1 se estourar o timeout.
wait_pane_settle() {
    local pane="$1" timeout_ms="${2:-8000}" interval_ms=400
    local waited=0 st
    while [ "$waited" -lt "$timeout_ms" ]; do
        st="$("$HERDR_BIN" agent explain "$pane" --json 2>/dev/null | python3 -c "
import sys,json
try: print(json.load(sys.stdin).get('state') or 'unknown')
except Exception: print('unknown')
" 2>/dev/null)"
        case "$st" in
            idle|done) return 0 ;;
        esac
        sleep 0.4
        waited=$((waited + interval_ms))
    done
    return 1
}
# cli = CLI Operator (system/orchestrator) — sem pane Herdr.


# ─── Funções utilitárias ──────────────────────────────────────────────────────
log()  { echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] $*"; }
ok()   { echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] ✅ $*"; }
warn() { echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] ⚠️  $*"; }
fail() { echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] ❌ $*" >&2; exit 1; }

hm_is_running() {
    # Retorna 0 (true) se o processo HerdMaster está vivo
    if [ -f "$HM_PID_FILE" ]; then
        local pid
        pid=$(cat "$HM_PID_FILE")
        kill -0 "$pid" 2>/dev/null && return 0
    fi
    return 1
}

hm_python() {
    DATABASE_URL="$HM_PG_URL" HERDMASTER_DB_SCHEMA="$HM_PG_SCHEMA" PYTHONPATH="$HM_ROOT/src${PYTHONPATH:+:$PYTHONPATH}" "$HM_PYTHON" "$@"
}

hm_pg_migrate_and_cleanup() {
    hm_python - <<'PY'
from herdmaster.db.schema import cleanup_orphan_hm_schemas, connect, init_db, migrate_all_agent_foreign_keys

conn = connect()
try:
    init_db(conn)
    migrated = migrate_all_agent_foreign_keys(conn)
    dropped = cleanup_orphan_hm_schemas(conn)
    print("migrated_schemas=" + ",".join(migrated))
    print("dropped_schemas=" + ",".join(dropped))
finally:
    conn.close()
PY
}

hm_pg_reset_all_hm_schemas() {
    hm_python - <<'PY'
from psycopg import sql
from herdmaster.db.schema import connect

conn = connect()
try:
    with conn._conn.cursor() as cur:
        cur.execute(
            """
            SELECT schema_name
            FROM information_schema.schemata
            WHERE schema_name LIKE 'hm\\_%%' ESCAPE '\\'
            ORDER BY schema_name
            """
        )
        schemas = [str(row["schema_name"]) for row in cur.fetchall()]
        for schema_name in schemas:
            cur.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema_name)))
    conn.commit()
    print("dropped_schemas=" + ",".join(schemas))
finally:
    conn.close()
PY
}

# ─── AÇÃO: status ─────────────────────────────────────────────────────────────
action_status() {
    log "=== STATUS DOS COMPONENTES ==="
    date -u

    echo ""
    log "--- HerdMaster Process ---"
    if hm_is_running; then
        local pid
        pid=$(cat "$HM_PID_FILE")
        ok "HerdMaster RUNNING | PID=$pid"
        ps -p "$pid" -o pid,etime,pcpu,pmem,cmd --no-header 2>/dev/null || true
    else
        warn "HerdMaster NOT RUNNING"
    fi

    echo ""
    log "--- Sockets ---"
    for sock in "$HM_SOCK" "$HM_API_SOCK"; do
        if [ -S "$sock" ]; then
            ok "Socket EXISTS: $sock ($(stat -c '%y' "$sock" 2>/dev/null | cut -d. -f1))"
        else
            warn "Socket MISSING: $sock"
        fi
    done

    echo ""
    log "--- Herdr Process ---"
    if pgrep -x herdr > /dev/null 2>&1; then
        ok "Herdr RUNNING (PID=$(pgrep -x herdr | head -1))"
        "$HERDR_BIN" workspace list 2>/dev/null | head -5 || true
    else
        warn "Herdr NOT RUNNING"
    fi

    echo ""
    log "--- Database (Postgres) ---"
    log "  url=$HM_PG_URL"
    log "  active_schema=$HM_PG_SCHEMA"
    hm_python - <<'PY' 2>/dev/null || warn "  Could not read Postgres stats"
from herdmaster.db.schema import connect

conn = connect()
try:
    print("  Task counts:")
    for row in conn.execute("SELECT state, COUNT(*) AS count FROM tasks GROUP BY state ORDER BY count DESC"):
        print(f"    {row['state']:15} {row['count']}")
finally:
    conn.close()
PY

    echo ""
    log "--- Agentes Registrados (DB) ---"
    hm_python - <<'PY' 2>/dev/null || warn "  Não foi possível ler agentes do Postgres"
from herdmaster.db.schema import connect

conn = connect()
try:
    for row in conn.execute("SELECT id, label, type, role, state, health, last_heartbeat FROM agents ORDER BY id"):
        print(f"  {row['label']:30} | pane={row['id']:8} | type={row['type']:6} | role={row['role']:12} | state={row['state']:8} | health={row['health']:8} | hb={row['last_heartbeat'] or 'nunca'}")
finally:
    conn.close()
PY

    echo ""
    log "--- Prompt Files Residuais ---"
    local count
    count=$(find "$HM_PROMPTS_DIR" -name "task-*.md" 2>/dev/null | wc -l)
    log "  Arquivos task-*.md pendentes: $count"
}


# ─── AÇÃO: start ─────────────────────────────────────────────────────────────
action_start() {
    log "=== START: Inicializando HerdMaster ==="

    if hm_is_running; then
        warn "HerdMaster já está rodando (PID=$(cat "$HM_PID_FILE")). Use 'restart' se quiser reiniciar."
        exit 0
    fi

    log "Preparando Postgres HerdMaster (schema ativo: $HM_PG_SCHEMA)..."
    hm_pg_migrate_and_cleanup

    log "Iniciando HerdMaster em background (com HTTP API em :8080)..."
    if command -v setsid >/dev/null 2>&1; then
        setsid -f "$HM_BIN" start --http > "$HM_CONFIG_DIR/herdmaster-stdout.log" 2>&1
    else
        nohup "$HM_BIN" start --http > "$HM_CONFIG_DIR/herdmaster-stdout.log" 2>&1 &
        disown || true
    fi


    log "Aguardando HerdMaster ficar pronto (até 15s)..."
    local attempts=0
    while [ $attempts -lt 15 ]; do
        sleep 1
        if hm_is_running; then
            ok "HerdMaster STARTED | PID=$(cat "$HM_PID_FILE")"
            sleep 2  # deixa o HM fazer sync inicial com o Herdr
            purge_unlisted_agents
            return 0
        fi

        attempts=$((attempts + 1))
    done

    fail "HerdMaster não iniciou em 15s. Verifique: $HM_CONFIG_DIR/herdmaster-stdout.log"
}

# ─── FUNÇÃO: purge de agentes não-documentados ───────────────────────────────
# Whitelist DINÂMICA: lê ~/.config/herdmaster/agent_whitelist.json (reescrito de
# hora em hora pelo reconciliador a partir do roster vivo do herdr). Fallback seguro
# para o roster vivo atual — NUNCA usa lista hardcoded obsoleta que apagaria agentes reais.
purge_unlisted_agents() {
    local deleted
    deleted=$(hm_python - <<'PY'
import json, os
from herdmaster.db.schema import connect

_wl_file = os.path.expanduser("~/.config/herdmaster/agent_whitelist.json")
try:
    with open(_wl_file, encoding="utf-8") as f:
        whitelist = tuple(str(x) for x in json.load(f) if str(x).strip())
    if not whitelist:
        raise ValueError("empty whitelist file")
except Exception:
    # Fallback seguro: roster vivo (cli + 8 panes w8). Não deletar agentes reais.
    whitelist = ("cli","w8:pJ","w8:pY","w8:pQ","w8:p14","w8:pG","w8:pS","w8:pR","w8:p12")

conn = connect()
try:
    cur = conn.execute("DELETE FROM agents WHERE id <> ALL(%s)", (list(whitelist),))
    conn.commit()
    print(cur.rowcount)
finally:
    conn.close()
PY
)
    if [ "${deleted:-0}" -gt 0 ]; then
        warn "purge_unlisted_agents: $deleted agente(s) fora da whitelist removido(s) do DB"
    fi
}



# ─── AÇÃO: stop ───────────────────────────────────────────────────────────────
action_stop() {
    log "=== STOP: Parando HerdMaster ==="

    if ! hm_is_running; then
        warn "HerdMaster não está rodando."
        return 0
    fi

    local pid
    pid=$(cat "$HM_PID_FILE")
    log "Enviando SIGTERM ao PID $pid..."
    kill -SIGTERM "$pid" 2>/dev/null || true

    log "Aguardando shutdown gracioso (até 10s)..."
    local attempts=0
    while [ $attempts -lt 10 ]; do
        sleep 1
        if ! kill -0 "$pid" 2>/dev/null; then
            ok "HerdMaster STOPPED (PID $pid encerrado)"
            rm -f "$HM_PID_FILE" "$HM_SOCK" "$HM_API_SOCK"
            return 0
        fi
        attempts=$((attempts + 1))
    done

    warn "Processo não encerrou em 10s. Forçando SIGKILL..."
    kill -SIGKILL "$pid" 2>/dev/null || true
    sleep 1
    rm -f "$HM_PID_FILE" "$HM_SOCK" "$HM_API_SOCK"
    ok "HerdMaster KILLED (forçado)"
}

# ─── AÇÃO: agents-flush ───────────────────────────────────────────────────────
action_agents_flush() {
    log "=== AGENTS FLUSH: reset de contexto + verificação via agent explain ==="

    if ! pgrep -x herdr > /dev/null 2>&1; then
        fail "Herdr não está rodando. Não é possível enviar comandos aos panes."
    fi

    load_agent_map || fail "Não foi possível carregar o roster vivo do herdr."
    log "Roster vivo carregado: ${#AGENT_MAP[@]} panes."

    for pane in "${!AGENT_MAP[@]}"; do
        local agent_name="${AGENT_MAP[$pane]}"
        local atype="${AGENT_TYPE[$pane]:-unknown}"
        local cmd; cmd="$(reset_cmd_for_type "$atype")"
        log "[$agent_name] pane=$pane (type=$atype) → 'herdr pane run' \"$cmd\" (texto+Enter)..."
        if ! "$HERDR_BIN" pane run "$pane" "$cmd" 2>/dev/null; then
            warn "  [$agent_name] run falhou (pane pode não existir)"; continue
        fi
        # Assenta event-driven (substitui sleep cego); fallback p/ sleep curto.
        wait_pane_settle "$pane" 8000 || sleep 1

        # ── Verificação por agent explain (autoridade única) ───────────────
        # ── Verificação (frota 100% screen-manifest) ───────────────────────
        # AUTORIDADE: agent explain --json (estado + regra/fallback, ciente do
        # tipo). Provado live (2026-06-27) que rastreia idle/working com precisão.
        # O read-back de TEXTO foi REBAIXADO a log informativo: depois de um reset
        # o eco do comando (e a confirmação do agente, ex.: AGY "new chat") fica
        # legitimamente visível no buffer, então `pane_reset_landed` dava
        # falso-suspeito e disparava recovery em pane saudável. NÃO é mais gate.
        local exp_line exp_rc
        exp_line="$(pane_explain_state "$pane" "$atype")"; exp_rc=$?
        if [ "$exp_rc" -eq 0 ]; then
            ok "  [$agent_name] limpo · explain=$exp_line"
        elif [ "$exp_rc" -eq 2 ]; then
            warn "  [$agent_name] BLOCKED · explain=$exp_line (requer atenção; sem recovery automático)"
        else
            warn "  [$agent_name] suspeito (explain=$exp_line rc=$exp_rc) → recovery"
            recover_stuck_pane "$pane" "$cmd"
            wait_pane_settle "$pane" 6000 || true
            exp_line="$(pane_explain_state "$pane" "$atype")"; exp_rc=$?
            if [ "$exp_rc" -eq 0 ]; then
                ok "  [$agent_name] recuperado · explain=$exp_line"
            else
                warn "  [$agent_name] AINDA suspeito após recovery · explain=$exp_line rc=$exp_rc · read-back: $(pane_tail "$pane" 2)"
            fi
        fi
        sleep 1
    done

    ok "Flush completo. Aguarde os agentes responderem antes de despachar novas tasks."
}

# ─── AÇÃO: restart ────────────────────────────────────────────────────────────
action_restart() {
    log "=== RESTART: Para + Reinicia (SEM apagar dados) ==="
    log "Dados preservados: DB, projetos, tasks, histórico"
    action_stop
    sleep 2
    action_start
    ok "Restart concluído. DB intacto."
}

# ─── AÇÃO: reset-soft ────────────────────────────────────────────────────────
action_reset_soft() {
    log "=== RESET SOFT: Para + Limpa resíduos + Reinicia ==="
    log "O que será APAGADO:"
    log "  - Prompt files residuais em $HM_PROMPTS_DIR/task-*.md"
    log "  - Sockets stale"
    log "O que será PRESERVADO:"
    log "  - Banco de dados (tasks, projetos, histórico)"
    log "  - Configuração (config.toml)"
    echo ""
    read -r -p "Confirmar reset-soft? [s/N] " confirm
    [[ "$confirm" =~ ^[sS]$ ]] || { log "Cancelado pelo operador."; exit 0; }

    action_stop
    sleep 1

    log "Limpando prompts residuais..."
    rm -f "$HM_PROMPTS_DIR"/task-*.md
    local removed=$?
    ok "Prompts limpos (exit=$removed)"

    log "Limpando sockets stale..."
    rm -f "$HM_SOCK" "$HM_API_SOCK" "$HM_PID_FILE"
    ok "Sockets removidos"

    sleep 1
    action_start

    log "Limpando contexto dos agentes no Herdr..."
    action_agents_flush

    ok "Reset soft completo."
}

# ─── AÇÃO: reset-hard ────────────────────────────────────────────────────────
action_reset_hard() {
    log "=== RESET HARD: Limpeza TOTAL — INÍCIO DO ZERO ==="
    warn "⚠️  ESTA AÇÃO É IRREVERSÍVEL"
    log "O que será PERMANENTEMENTE APAGADO:"
    log "  - Schemas Postgres hm_* em $HM_PG_URL (tasks, projetos, agentes)"
    log "  - Arquivos SQLite legados se existirem: $HM_DB / $HM_DB_WAL / $HM_DB_SHM"
    log "  - Todos os prompt files em $HM_PROMPTS_DIR/"
    log "  - Todos os sockets e PID file"
    log "O que será PRESERVADO:"
    log "  - config.toml (configuração do sistema)"
    log "  - Processos Herdr e seus panes (apenas contexto será limpo via /chat new)"
    echo ""
    read -r -p "⚠️  CONFIRMAR RESET HARD? [Digite CONFIRMO para prosseguir] " confirm
    [[ "$confirm" == "CONFIRMO" ]] || { log "Cancelado. Reset hard NÃO executado."; exit 0; }

    log "Iniciando reset hard..."
    action_stop
    sleep 2

    log "Apagando schemas HerdMaster no Postgres..."
    hm_pg_reset_all_hm_schemas
    ok "Schemas Postgres hm_* apagados"

    log "Apagando arquivos SQLite legados se existirem..."
    rm -f "$HM_DB" "$HM_DB_WAL" "$HM_DB_SHM"
    ok "Arquivos SQLite legados apagados"

    log "Apagando prompts residuais..."
    rm -f "$HM_PROMPTS_DIR"/task-*.md
    ok "Prompts apagados"

    log "Apagando sockets e PID..."
    rm -f "$HM_SOCK" "$HM_API_SOCK" "$HM_PID_FILE"
    ok "Sockets e PID removidos"

    sleep 1

    log "Reiniciando HerdMaster (novo DB será criado automaticamente)..."
    action_start

    log "Limpando contexto de todos os agentes..."
    action_agents_flush

    ok "Reset hard concluído. Sistema está do zero."
    log "Próximo passo: criar um novo projeto com:"
    log "  herdmaster projects create 'Nome do Projeto' --scope 'Descrição do escopo'"
}

# ─── MAIN ─────────────────────────────────────────────────────────────────────
ACAO="${1:-}"

case "$ACAO" in
    start)        action_start ;;
    stop)         action_stop ;;
    restart)      action_restart ;;
    reset-soft)   action_reset_soft ;;
    reset-hard)   action_reset_hard ;;
    status)       action_status ;;
    agents-flush) action_agents_flush ;;
    *)
        echo ""
        echo "HerdMaster OPS Bootstrap"
        echo "Uso: bash bootstrap.sh <acao>"
        echo ""
        echo "Ações disponíveis:"
        echo "  status        → Estado atual de todos os componentes (sem alterar nada)"
        echo "  start         → Inicia o HerdMaster (primeira vez ou após stop limpo)"
        echo "  stop          → Para o HerdMaster de forma ordenada (SIGTERM → SIGKILL)"
        echo "  restart       → Para + Reinicia SEM apagar dados"
        echo "  agents-flush  → Envia /chat new para todos os panes (limpa contexto dos agentes)"
        echo "  reset-soft    → Para + Limpa prompts residuais/sockets + Reinicia (preserva DB)"
        echo "  reset-hard    → Para + Apaga DB completo + Reinicia do zero (IRREVERSÍVEL)"
        echo ""
        echo "Ordem recomendada para início do zero:"
        echo "  1. bash bootstrap.sh status          ← Diagnóstico primeiro"
        echo "  2. bash bootstrap.sh reset-hard      ← Se quiser limpar tudo"
        echo "  3. bash bootstrap.sh agents-flush    ← Limpar contexto dos agentes"
        echo "  4. herdmaster projects create ...    ← Criar novo projeto"
        echo ""
        exit 1
        ;;
esac
