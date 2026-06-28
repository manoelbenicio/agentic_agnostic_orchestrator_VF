# 55 — Guia Herdr para o Tech Lead (operação da squad)

> Manual operacional de como o Tech Lead (Kiro-Opus-4.8) controla, delega e
> verifica a squad pelo Herdr. A squad roda toda dentro do workspace `w3`.
> **Os IDs de pane podem mudar** quando panes/abas são fechados — sempre releia
> com `herdr agent list` / `herdr pane list` antes de delegar; nunca chumbe IDs.

---

## 1. Regra de ouro: `agent send` NÃO envia — falta o Enter

`herdr agent send <pane> "texto"` **apenas digita** o texto no input do agente.
Ele **não** submete. Sem o Enter, a tarefa fica **parada** no input e o agente
**não faz nada** (sintoma: "todas paradas").

**Padrão correto — sempre os dois passos:**

```bash
herdr agent send w3:p3 "sua tarefa aqui"
herdr pane send-keys w3:p3 enter
```

Ou em uma linha:

```bash
herdr agent send w3:p3 "sua tarefa aqui" && herdr pane send-keys w3:p3 enter
```

**Mensagem em bloco único:** mande o prompt como **uma única linha** (sem quebras
de linha "de verdade"). Newlines embutidos podem submeter cedo demais na TUI e
quebrar a mensagem. Use `;` ou ` | ` como separadores dentro do texto.

---

## 2. Verificar a entrega (não confie, confira)

Depois do Enter, confirme que o agente realmente recebeu e começou a processar:

```bash
herdr pane read w3:p3 --source recent --lines 15
```

- Se aparecer o agente **processando** (e o status virar `working`) → entregou.
- Se aparecer **o seu texto parado no input** → faltou o Enter; mande
  `herdr pane send-keys w3:p3 enter`.

Para logs longos use `--source recent-unwrapped` (ignora soft-wrap).

---

## 3. Status da squad

```bash
herdr agent list          # agent_status de cada agente: idle/working/done/blocked
herdr pane list           # panes existentes no workspace
```

- `done` = o agente terminou **mas você ainda não olhou** a pane. Leia com
  `pane read` e dê o próximo passo / handoff.
- `idle` = livre para receber tarefa.
- `working` = ocupado (não mande tarefa em cima).
- `blocked` = travado (precisa de intervenção — ex.: login).

> Observação local: para os agentes de detecção por tela (codex/agy/kiro),
> `herdr wait agent-status <pane> --status idle` se mostrou **não confiável**.
> Para "esperar ficar idle", faça polling com
> `herdr agent explain <pane> --json`. `--status working` e `--status done`
> funcionam bem para transições.

---

## 4. Antes de delegar: confirme idle E contexto certo

Antes de mandar qualquer tarefa para um agente:

1. `herdr agent list` → o agente está `idle`?
2. `herdr pane read <pane> --source recent --lines 20` → ele está no contexto do
   projeto **/mnt/c/VMs/Projects/AOP**? (Alguns seats podem estar ocupados com
   trabalho NÃO relacionado, ex.: transcrição/meeting notes em
   `/home/dataops-lab`. Se estiver, **não mande em cima** — anote e reporte.)

Sempre instrua o agente a operar a partir de `/mnt/c/VMs/Projects/AOP`
(caminhos absolutos ou `cd` para a pasta).

---

## 5. Seats deslogados / sem token (rotação de contas)

Sintoma: a pane do Codex aparece **vazia** ou com mensagem tipo
"logged out / signed in to another account" / "usage limit reached".

- **NÃO insista** enviando tarefa para um seat deslogado/sem token.
- Faça o fluxo de **device-login/OAuth** (única forma de auth permitida) e
  **passe a URL de login para o coordenador repassar ao usuário**.
- Prioridade por expertise do modelo: **Codex → Opus → Antigravity**.
- Cota = janela de 5h × X milhões de tokens (cada empresa tem a sua).
- Ver `docs/30-COMPONENTES/36-ROTACAO-CONTAS-TOKEN.md`.

---

## 6. Mapa atual da squad (releia sempre — pode mudar)

| Pane    | Agente                 | Papel típico                       |
|---------|------------------------|------------------------------------|
| w3:p1   | kiro (Opus 4.8) — **TL** | planeja, atribui, verifica, handoff |
| w3:p3   | codex                  | executor                           |
| w3:p4   | codex                  | executor                           |
| w3:p5   | codex                  | executor                           |
| w3:p6   | codex                  | executor                           |
| w3:p8   | codex                  | executor                           |
| w3:p7   | agy (Antigravity)      | executor (docs/verificação)        |

Confirme com `herdr agent list` antes de usar.

---

## 7. Receitas úteis

**Delegar e confirmar:**
```bash
herdr agent send w3:p3 "TAREFA: ... ; arquivos: ... ; criterio de verificacao: ..." \
  && herdr pane send-keys w3:p3 enter
sleep 3
herdr pane read w3:p3 --source recent --lines 15
```

**Ler o que um agente produziu quando ficou `done`:**
```bash
herdr pane read w3:p5 --source recent --lines 80
```

**Esperar uma transição confiável (working/done):**
```bash
herdr wait agent-status w3:p3 --status done --timeout 120000
```

---

## 8. Lembretes de papel do TL

- O TL **planeja, atribui, verifica execução e garante handoff** em troca de
  agente. O TL **nunca produz código**, nem em tempo ocioso.
- Serviços **zumbis NÃO devem ser mortos automaticamente** — identifique e
  **reporte ao usuário** para decisão conjunta.
- Política de portas: porta nativa ocupada → **+5** → testa → se livre, usa e
  **documenta como novo padrão** (objetivo: não quebrar outros projetos).
- Toda a comunicação do coordenador é **somente com o TL**; o TL distribui aos
  agentes via injeção direta (`agent send` + Enter).
