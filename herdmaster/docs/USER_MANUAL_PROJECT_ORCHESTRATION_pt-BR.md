# Manual do Usuário: Orquestração de Projetos e Tarefas

Este manual de operações detalha a Experiência do Usuário (UX) no dia a dia (Day 2) com o ecossistema Herdr + HerdMaster. O foco é explicar *como* despachar tarefas individuais e *como* usar o Modo Projeto (onde um agente atua como Tech Lead para distribuir o trabalho).

## 1. Filosofia de Interface (UX)

**Uma pergunta comum:** *"Foram criados novos menus dentro do aplicativo do Herdr para gerenciar os projetos?"*

**A resposta é NÃO.** O Herdr continua sendo um multiplexador de terminal puro (uma infraestrutura limpa, similar ao `tmux`). Não poluímos a interface do Herdr com botões de gestão.

Todo o controle, delegação e aprovação é feito via **HerdMaster CLI** (Interface de Linha de Comando do Orquestrador), que pode ser executado em qualquer aba de terminal, independentemente de estar dentro ou fora do Herdr.

Pense assim:
* **Herdr:** É o vidro (a tela) e as cadeiras onde os Agentes (A1, A2...) sentam para trabalhar.
* **HerdMaster:** É o controle remoto que você (o humano) usa para dar ordens a esses agentes.

---

## 2. Modo Tarefa (Atribuição Direta)

Se você já sabe o que quer fazer e quer designar o trabalho para um agente específico (ex: um worker de Python na janela 2), você usa o comando `tasks`.

### Criar uma tarefa:
Você despacha o prompt (a instrução) direto para o banco de dados. O *Task Queue* vai pegar essa tarefa e jogar na tela do agente assim que ele estiver ocioso.

```bash
herdmaster tasks create "Refatorar API" \
  --prompt "Abra o arquivo main.py e refatore a rota de login para usar JWT." \
  --priority high \
  --assigned-to A2
```
* **`--priority`**: Pode ser `low`, `normal`, `high`, `critical`.
* **`--assigned-to`**: Força a tarefa a cair para o agente `A2` (Janela 2 do Herdr). Se omitido, cai para o primeiro agente livre.

### Listar tarefas:
```bash
herdmaster tasks list
```
Isso imprimirá uma tabela no seu terminal com todas as tarefas, mostrando se estão `queued` (na fila), `in_progress` (rodando na tela do agente) ou `done` (concluída).

---

## 3. Modo Projeto (Orquestração via Tech Lead)

No Modo Projeto, você não diz aos *workers* o que fazer. Você entrega um grande escopo (*scope*) para o Agente Orquestrador (Tech Lead, geralmente o `A1`). Ele analisa o escopo, quebra em sub-tarefas e devolve o plano para você aprovar.

### Passo 3.1: Enviar o Projeto para o Tech Lead
```bash
herdmaster projects create "Novo Portal Web" \
  --scope "Construa um portal web em React. Precisa ter login, tela de dashboard e chamadas para nossa API local." \
  --orchestrator-id A1
```
*Neste momento:*
1. O HerdMaster salva o projeto como `awaiting_analysis`.
2. O HerdMaster "digita" automaticamente na tela do agente `A1` (Tech Lead) dentro do Herdr, pedindo para ele quebrar esse projeto em tarefas.
3. O agente `A1` responde com um plano JSON.
4. O projeto muda para o status `awaiting_approval`.

### Passo 3.2: Verificar o status do projeto
```bash
herdmaster projects list
```
Você verá o projeto "Novo Portal Web", sua complexidade calculada pela IA (ex: Alta, Baixa), e a estimativa de horas (`ETA Hours`).

### Passo 3.3: Aprovar o Plano do Tech Lead
O humano sempre tem a palavra final. Se o plano feito pelo `A1` fizer sentido, você aprova. Opcionalmente, pode rejeitar ou modificar as *notes* do projeto.

```bash
herdmaster projects approve <ID_DO_PROJETO> --decision accept
```
*Neste momento:*
O HerdMaster pega as sub-tarefas geradas pelo plano do A1 e as insere na *Task Queue* automaticamente. A partir daí, os agentes trabalhadores (`A2`, `A3`, `A4`) vão começar a puxar as tarefas, e as telas do Herdr vão começar a "piscar" com eles trabalhando em paralelo!

---

## 4. Conclusão da Experiência

O fluxo E2E foi desenhado para manter o Operador (Você) no Terminal, usando comandos legíveis (`herdmaster tasks ...` e `herdmaster projects ...`). 

Ao abrir o **Herdr** na sua tela secundária, você atua apenas como um "Deus Observador". Você verá o HerdMaster digitando nas abas, os agentes pensando, os comandos rodando, e o código sendo gerado, sem precisar tocar em nada.
