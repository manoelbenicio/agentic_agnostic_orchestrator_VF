# 32 — Web Frontend (Next.js)

Origem da verdade: `web/package.json`, `web/src/app/` (App Router), `web/src/app/globals.css`.

## 1. Stack

- **Next.js 16.2.9** (App Router), **React 19.2.7**.
- **@xyflow/react 12.11.1** — canvas de nós/arestas do **Squad Builder** (topologia da squad).
- **Tailwind CSS 4.3.1** (+ `@tailwindcss/postcss`), **TypeScript 6.0.3**.
- UI: `@radix-ui/react-slot`, `class-variance-authority`, `clsx`, `tailwind-merge`, `cmdk` (command palette), `lucide-react` (ícones), `next-themes` (dark mode).

Scripts (`package.json`): `dev` (`next dev`), `build`, `start`, `lint`.

Sobe via `start.sh`:
```
NEXT_PUBLIC_API_URL="http://127.0.0.1:8090" npm run dev -- --hostname 127.0.0.1 --port 13000
```

---

## 2. Rotas (App Router — `web/src/app/`)

| Rota | Propósito (pelo nome/área) |
|------|----------------------------|
| `/` | dashboard inicial |
| `/agents` | gestão de agentes (registry) |
| `/squad-builder` | montagem visual da squad/topologia (xyflow) |
| `/projects` | projetos (e Kanban de tarefas) |
| `/finops` | dashboards de custo (FinOps) |
| `/observability` | KPIs/observabilidade |
| `/live` | stream em tempo real (WebSocket de tracing) |
| `/sessions` | sessões de agentes |
| `/seats` | seats/assinaturas |
| `/inbox` | caixa de entrada de mensagens |
| `/issues` | tracker de issues/tarefas |
| `/my-issues` | issues atribuídas ao usuário |
| `/settings` | configurações |

> Confirme a lista viva navegando ou listando `web/src/app/*/page.tsx`. Cada rota consome o control-plane via `NEXT_PUBLIC_API_URL`.

### Verificação

```bash
find web/src/app -name 'page.tsx' | sed 's#web/src/app##; s#/page.tsx##; s#^$#/#' | sort
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:13000
```

---

## 3. Design System — Indra DSS v3.0 (HEX obrigatório)

Tokens canônicos em `web/src/app/globals.css`. **Regra inviolável: hexadecimal apenas — NUNCA OKLCH**, sem substituição/aproximação.

Swatches Indra (extraídos do arquivo):
```
deep #002B3A · dark #003E50 · primary #06596E · secondary #346679
cyan #00B0BD (hero accent) · teal #3F96AE · light #7A9CAE
blue-gray #B3C1DA · sky #BADFF3 · warm #B0B4BD · off #E8E8E1
off-white #F2F5F6 · white #FFFFFF · ink #00475A · gray #65655F · line #C7CBC5
success #27AE60 · warning #FF9800 · error #E91E63 · gold #FFC107
```

Tokens semânticos (`:root` claro / `.dark` escuro), p.ex.:
- `--background`, `--surface`, `--foreground`, `--primary`, `--accent` (cyan), `--destructive` (error), `--success`, `--warning`, `--gold`, `--border`, `--ring`.
- `--radius: 0.625rem`; sombras em `--shadow-card`.
- Fontes: `--font-sans` (Inter), `--font-mono` (Geist Mono).
- Classes utilitárias: `.aop-card`, `.aop-focus`, animações `.aop-fade-in`/`.aop-float-in`/`.aop-wipe-in`.

> Qualquer componente novo **deve** consumir essas variáveis CSS (via `@theme inline` mapeado para classes Tailwind `--color-*`). Introduzir cores OKLCH ou hex fora da paleta é violação do DSS.

### Verificação (sem OKLCH)

```bash
# Não pode haver oklch() no CSS do design system:
grep -ri 'oklch' web/src/app/globals.css && echo "VIOLACAO DSS" || echo "OK (sem OKLCH)"
```

---

## 4. Integração com backend

- Base da API: `process.env.NEXT_PUBLIC_API_URL` (= `http://127.0.0.1:8090`).
- Tempo real (`/live`): WebSocket em `ws://127.0.0.1:8090/ws/tracing/agents/{id}`.
- FinOps (`/finops`): consome `GET /finops/projects/{tenant}/{project}/rollup` e (futuramente) breakdown por modelo/Kanban — ver doc 35.

> **Lacuna de produto a observar:** o breakdown granular de FinOps (por modelo, Kanban, grupo de TL/agente) ainda **não** tem endpoint dedicado no backend; o frontend hoje só tem o rollup por tenant/projeto. Roadmap em doc 35 + pesquisa em doc 92.
