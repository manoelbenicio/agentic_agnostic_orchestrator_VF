# 53 — Protocolo de Check-In / Check-Out (OBRIGATÓRIO)

> **Requisito do produto (inegociável):** todo agente, **antes** de iniciar qualquer atividade, registra no ledger em disco: **nome do agente + timestamp**. Ao **terminar**, registra: **nome do agente + timestamp + evidência da entrega**.

## 0. Por que o ledger existe (no modelo de TL)

Você levantou: "se eu mando todas as tarefas direto para o TL, preciso mesmo de um controle de check-in?". Resposta: **sim, mas como ferramenta do TL — não como burocracia do worker.**

O roteamento (tudo → TL) resolve *quem recebe*; o ledger resolve outra coisa que o TL **é obrigado** a fazer (doc 54 §0): **verificar se o que foi atribuído foi realmente executado** e **garantir o handoff** na troca de agente. Sem um registro em disco, o TL não tem como provar conclusão nem passar o bastão sem perda.

Como fica no modelo de TL:
- O **TL** registra a **atribuição** (quem vai fazer o quê) e depois o **resultado verificado** (com evidência). O ledger é o diário de bordo do TL.
- O worker não precisa de cerimônia: ao terminar, devolve a **evidência** ao TL; o TL fecha a linha no ledger.
- Em **troca de agente** (ex.: rotação de conta por esgotamento — doc 36), a linha de handoff no ledger é o que garante continuidade.

> Em uma frase: o ledger não é "ponto eletrônico" do worker — é o **registro de verificação e handoff do TL**. Se preferir, os workers nem escrevem nele; o **TL** escreve as atribuições e os check-outs verificados.

---

## 1. Onde fica o ledger

Arquivo único em disco, no diretório do projeto:

```
/mnt/c/VMs/Projects/AOP/CHECKIN_OUT.md
```

> Este é o **novo** ledger canônico. O legado (`OLD/CHECKIN_OUT.md`, e o `CHECKIN_OUT_GSD.md` referenciado pelo `status360.py`) **não** deve ser usado. Um template inicial já foi criado (ver §5).

## 2. Formato (tabela append-only)

Cada linha é um evento. **Nunca** reescrever linhas antigas — só **adicionar** (append). Colunas:

```
| timestamp_utc | agente | tipo | onda | escopo/arquivos | status | evidência |
```

| Campo | Regra |
|-------|-------|
| `timestamp_utc` | `date -u +%Y-%m-%dT%H:%M:%SZ` (UTC, ISO-8601) |
| `agente` | identificador estável (ex.: `TL`, `CDX-1`, `GEM-1`, `GLM-1`) |
| `tipo` | `CHECK-IN` ou `CHECK-OUT` |
| `onda` | número da onda (doc 52), ex.: `1` |
| `escopo/arquivos` | diretórios/arquivos que o agente vai tocar (disjunção!) |
| `status` | `IN-PROGRESS` (no check-in) · `COMPLETA`/`FALHA`/`BLOQUEADA` (no check-out) |
| `evidência` | **obrigatória no check-out**: comando+saída, hash de commit, link de PR, caminho de arquivo, screenshot |

## 3. O que conta como "evidência" (check-out)

A evidência precisa ser **reproduzível e verificável pelo TL**. Exemplos aceitos:
- Hash de commit + branch (`git rev-parse HEAD`).
- Saída de `smoke_e2e.py` (`result: passed` + checks).
- Caminho de arquivo gerado + `sha256sum`.
- Resultado de comando de verificação dos docs (ex.: `curl .../health` com saída).
- Screenshot anexado (caminho no repo) para itens de UI.

> Check-out **sem** evidência reproduzível é **inválido**. O TL rejeita e a tarefa permanece aberta.

## 4. Exemplo de uso (commands)

```bash
LEDGER=/mnt/c/VMs/Projects/AOP/CHECKIN_OUT.md
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)

# CHECK-IN (antes de começar):
printf '| %s | CDX-1 | CHECK-IN | 1 | control-plane/executors/ | IN-PROGRESS | - |\n' "$TS" >> "$LEDGER"

# ... trabalho ...

# CHECK-OUT (ao terminar, com evidência):
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
COMMIT=$(git rev-parse --short HEAD)
printf '| %s | CDX-1 | CHECK-OUT | 1 | control-plane/executors/ | COMPLETA | commit %s; smoke=passed |\n' "$TS" "$COMMIT" >> "$LEDGER"
```

## 5. Template inicial

Foi criado o arquivo `CHECKIN_OUT.md` na raiz do projeto com o cabeçalho da tabela e as regras resumidas. Os agentes apenas **adicionam linhas** abaixo do cabeçalho.

## 6. Regras de disciplina

1. **Sem check-in → proibido tocar em código.** Trabalho sem check-in é descartado.
2. **Check-in declara escopo;** tocar fora do escopo declarado = violação (TL reverte).
3. **Um escopo, um dono, por onda** (disjunção — doc 52).
4. **Check-out só com evidência** verificável.
5. **Append-only:** correções entram como **novas** linhas (ex.: um novo CHECK-OUT `FALHA` seguido de re-trabalho), nunca editando o histórico.
6. **O TL audita o ledger** ao fim de cada onda e arquiva um snapshot (ver doc 54).

## 7. Verificação

```bash
LEDGER=/mnt/c/VMs/Projects/AOP/CHECKIN_OUT.md
# Todo CHECK-IN tem um CHECK-OUT correspondente? (auditoria simples por agente)
grep CHECK-IN "$LEDGER" | wc -l
grep CHECK-OUT "$LEDGER" | wc -l
# Check-outs sem evidência (coluna evidência == '-' ou vazia) são inválidos:
awk -F'|' '/CHECK-OUT/ && ($8 ~ /^[[:space:]]*-?[[:space:]]*$/){print "SEM EVIDENCIA:",$0}' "$LEDGER"
```
