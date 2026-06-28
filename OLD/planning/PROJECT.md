# PROJECT.md — Agnostic Orchestration Platform (AOP)

## Visão
Plataforma Enterprise Agnóstica de Orquestração de Agentes de IA — orquestra CLIs de agente
(Codex, Kiro, Antigravity, Gemini…) por seats de assinatura, dois modos de operação por tarefa
(terminal/multiplexer e socket/control-plane), Tech-Lead com fan-out, FinOps, observabilidade e
um Visual Squad Builder. Web app disruptivo, **menu lateral esquerdo**, efeitos premium, nível Fortune 500.

## Stack
- Frontend: Next.js (App Router) + Tailwind v4 + shadcn/ui + @xyflow/react.
- Control-plane: FastAPI (:8090) reutilizando HerdMaster (Python) + Herdr (multiplexer).
- Dados: Postgres (unificado) + Redis. Observabilidade: Prometheus/Grafana/Alertmanager.

## Design System (MANDATÓRIO)
Indra DSS v3.0 — **HEXADECIMAL only** (sem OKLCH). Tokens em `AOP/web/src/app/globals.css`.
deep `#002B3A` · dark `#003E50` · primary `#06596E` · **cyan `#00B0BD` (accent)** · teal `#3F96AE`
sky `#BADFF3` · ink `#00475A` · line `#C7CBC5` · success `#27AE60` · warning `#FF9800` · error `#E91E63` · gold `#FFC107`.

## Princípios / Constraints
- ZERO mock/placeholder em produção (vazio = empty state real via API).
- 100% agêntico: 6 agentes, paths isolados, ondas de dispatch.
- Governança: CHECK-IN antes de iniciar + CHECK-OUT ao terminar com **timestamp + nome do agente + PRINT real** em `CHECKIN_OUT_GSD.md` (raiz). Sem print = inválido.
- GSD: Discuss → Plan → Execute → Verify → Ship em cada fase.

## Roadmap (resumo) — detalhe em ROADMAP.md e phases/*/SPEC.md
F0 Design System+Shell · F1 Projects · F2 Issues/Tasks · F3 Squad Builder+Agents ·
F4 Seats+Sessions · F5 FinOps+Observability+Live · F6 Settings+Inbox+My Issues+Search · F7 E2E+UI Review.

## Estado atual (baseline já entregue)
Control-plane integrado (:8090, coupling connected), Postgres/Redis, observabilidade, smoke E2E ok.
Frontend tem hoje só Dashboard/Squad Builder/Live — as demais telas são o objeto deste replanejamento.
