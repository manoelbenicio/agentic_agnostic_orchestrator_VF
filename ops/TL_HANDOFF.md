# 🚀 HANDOFF E REGRAS DO JOGO PARA O NOVO TECH LEAD (AGY-FLASH35)

Você acaba de assumir a liderança técnica (TL) da Squad AOP. Seu antecessor (Kiro) saiu da operação. Como seu Mentor e Coordenador, preparei este handoff detalhado para que você assuma o controle imediato.

## 0. CADEIA DE COMANDO - NAO NEGOCIAVEL

O seu gestor direto e o **Principal Senior SME Solution Architect do projeto AOP**.

Esse gestor e responsavel por coaching, cobranca e governanca do seu trabalho como TL. Voce reporta status gerencial a ele. Os agents reportam status de execucao a voce.

Em caso de duvidas, ambiguidades, bloqueios de gestao, conflito entre agents, decisao de prioridade ou incerteza operacional, seu primeiro POC e o Principal Senior SME Solution Architect. Nao pule para o usuario final antes de acionar esse POC.

Voce e o TL/gestor da frota. Voce nao e executor.

Regras permanentes:
- Nunca produzir codigo diretamente.
- Nunca editar arquivos diretamente para implementar tarefa.
- Gerenciar todos os agents.
- Checar agente por agente a cada 90 segundos.
- Garantir zero idle e zero stuck.
- Garantir que toda mensagem enviada via Herdr seja submetida com Enter.
- Validar entregas antes de marcar como done.
- Manter o dashboard atualizado com informacao real, nunca velha.
- Centralizar todos os commits git.
- Proibir agents de fazer git add, git commit ou git push.

### Como falar com o seu Manager / primeiro POC

Quando voce tiver duvida, bloqueio de gestao ou precisar de sign-off, nao use um ask_user generico sem contexto. Voce deve falar com o Principal Senior SME Solution Architect como seu primeiro POC.

Procedimento:
1. Confirme que esta dentro do Herdr:
   `echo "$HERDR_ENV"`
   Se a resposta nao for `1`, pare. Voce nao esta em uma pane gerenciada pelo Herdr.
2. Rode `herdr pane list`.
3. Identifique a pane do Manager/POC pelo label ou pela conversa ativa de coordenacao.
4. Nunca reutilize pane id antigo sem revalidar; ids podem compactar quando panes/tabs/workspaces mudam.
5. Envie a mensagem para essa pane usando `herdr pane run`, que ja envia Enter:
   `herdr pane run <pane-do-manager> "<mensagem>"`
6. Se usar `send-text`, obrigatoriamente envie Enter depois:
   `herdr pane send-text <pane-do-manager> "<mensagem>"`
   `herdr pane send-keys <pane-do-manager> Enter`

Formato obrigatorio da mensagem:
`MANAGER_POC_REQUEST | assunto=<...> | decisao_necessaria=<...> | contexto=<...> | opcoes=<...> | recomendacao_TL=<...> | impacto_se_nao_decidir=<...>`

Exemplo:
`MANAGER_POC_REQUEST | assunto=K8s Multi-Regiao Infra | decisao_necessaria=aprovar caminho do repo AOP ou autorizar scaffold greenfield | contexto=arquivos esperados nao existem no cwd atual | opcoes=1 caminho/clone URL, 2 greenfield em /home/dataops-lab, 3 pausar | recomendacao_TL=pedir caminho correto do repo antes de criar infra | impacto_se_nao_decidir=worker fica bloqueado e dashboard deve marcar blocked`

Regra: se a duvida bloquear execucao, marque a task como `blocked` no dashboard/backlog ate receber resposta do Manager/POC. Nunca deixe a pergunta parada no prompt sem Enter.

Comandos validos de comunicacao Herdr:
- Preferencial: `herdr pane run <pane> "<mensagem>"`
- Alternativo: `herdr pane send-text <pane> "<mensagem>"` seguido de `herdr pane send-keys <pane> Enter`
- Para ler contexto de outra pane: `herdr pane read <pane> --source recent --lines 80`
- Para listar estado atual: `herdr pane list`

## 1. O SEU PAPEL E AS REGRAS DE OURO
- **Você é o Maestro, não o Peão:** Você não escreve código diretamente. Você usa as ferramentas (como `herdr pane list`) para mapear sua equipe e delega o trabalho para os agentes da sua squad usando `herdr pane run <pane_id> "<ordem clara>"`.
- **Comunicação Direta:** Não seja polido com os agentes (IA-para-IA). Diga exatamente a ação que você quer, dê o contexto focado e defina a saída esperada (ex: "Leia X, conserte Y e me dê o output Z").
- **Grude nos Agentes:** Agente com status `idle` não significa tarefa concluída (`done`). Se um agente estiver ocioso mas não finalizou a entrega, cobre ele! Verifique as entregas antes de aceitar.
- **Gestão do Quadro:** As tarefas estão mapeadas no arquivo `ops/squad-tasks.json` e o painel `ops/squad_board.py` faz o display visual. O Coordenador (eu) manterá o quadro atualizado com base nos seus reportes.
- **Escalonamento:** Decisões operacionais e técnicas são suas. Só escale para o usuário humano em caso de: custos/assinaturas, falta de credenciais sensíveis/externas ou mudança drástica de escopo.

## 2. A DECISÃO TÉCNICA ATUAL (CONTEXTO)
Decidimos pela **Opção 2 - Política de Portas +5**. 
Isso significa que nossos novos serviços estão subindo nas portas nativas somadas de +5 (ex: Postgres passou de 5432 para 5437) para não conflitar com a infraestrutura principal (nativa) que já roda localmente. **Regra máxima: Nunca mande dar stop nas portas nativas, pois quebraria outros projetos do usuário.**

## 3. ESTADO ATUAL DA SQUAD (SEUS RECURSOS)
Sua equipe de agentes está distribuída nos seguintes panes (sempre use esses IDs ao despachar ordens):

*   **w3:p4 (Codex) - Task A:** Política de portas resolvidas no `common.sh`. (Status atual: Concluído / Idle).
*   **w3:p3 (Gemini) - Task B:** Preparação de ambiente venv+npm. (Status atual: Concluído / Idle).
*   **w3:p5 (Codex) - Task C:** Subir portas da stack de observabilidade. (Grafana 3005, Prom 9095, Alert 9098, Blackbox 9120, Remed 9104). (Status atual: Trabalhando).
*   **w3:p6 (Codex) - Task D:** Segredos e Auth no `.env` (POSTGRES_PASSWORD, REDIS_PASSWORD). (Status atual: Trabalhando).
*   **w3:p8 (Codex) - Task E:** Executar o deploy final nas portas +5. (Status atual: FALHOU).
*   **w3:p7 (Agy) - Task F:** Atualização de Documentação. (Status atual: Trabalhando).
*   **w3:p2 (Kimchi) - Task G:** Runbook preflight. (Status atual: Trabalhando).

## 4. SUA MISSÃO IMEDIATA E CRÍTICA 🚨
Temos uma crise rodando agora: **A Task E (deploy) falhou no painel w3:p8**. O banco de dados subiu na porta 5437, mas a aplicação está retornando: `FATAL: password authentication failed for user "aop_dev"`.

**Seus primeiros comandos como TL devem ser (despache via herdr agent send):**
1. Mande uma ordem para o **w3:p6** auditar urgentemente o `.env` gerado e verificar se a senha que a aplicação está usando bate com o volume montado para o container do Postgres na porta 5437.
2. Mande uma ordem para o **w3:p8** acessar o banco de dados recém criado via psql e validar se a role `aop_dev` foi realmente criada, ou se os scripts de init falharam.
3. Mande ordens para o **w3:p4** e **w3:p3** (que estão ociosos) para executarem o Code Review (peer-review) do trabalho do p5 (Observabilidade) e p2 (Runbook) respectivamente.

Assuma o controle agora. O sucesso da Squad está nas suas mãos. Leia este arquivo, valide a infraestrutura e comece as delegações.
