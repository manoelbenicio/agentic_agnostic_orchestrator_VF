# Auditoria Executiva de Telas e Rotas (AOP Web)

## Resumo Executivo
Foi realizada uma varredura completa em `AOP/web/src/app/**` para mapear todas as rotas da aplicação, verificando se a tela está funcional consumindo API real, ou se é apenas um placeholder/empty state (com dados simulados por falta de backend).
Constatou-se que a maior parte do core (Projects, Issues, FinOps, Seats, etc.) já consome API real. Telas operacionais e de configuração (Inbox, Settings, My Issues) possuem layout finalizado com empty states, mas simulam chamadas de API, aguardando o desenvolvimento de seus respectivos endpoints no control-plane.

## Tabela de Rotas

| Caminho | Existe `page.tsx`? | Estado | Evidência (Trechos) | Severidade | Ação Recomendada | Dono (AG) |
|---|---|---|---|---|---|---|
| `/` | Sim | consome-API-real | `import { FinOpsPanel } ... export default function Home()` | P2 | Manter monitoramento | AG-1 |
| `/agents` | Sim | consome-API-real | `const response = await fetch(\`\${apiBase}/agents\`...` | P2 | Nenhuma ação imediata | AG-3 |
| `/finops` | Sim | consome-API-real | `fetch(\`\${apiBase}/projects\`) ... fetch(\`\${apiBase}/seats\`)` | P2 | Nenhuma ação imediata | AG-5 |
| `/inbox` | Sim | vazia/placeholder | `// Simulando fetch de API real ... setEvents([]);` | P1 | Desenvolver API `/api/inbox` no backend e plugar na UI | AG-6 |
| `/issues` | Sim | consome-API-real | `const response = await fetch(\`\${apiBase}/issues\`...` | P2 | Nenhuma ação imediata | AG-2 |
| `/live` | Sim | consome-API-real | `const res = await fetch(\`\${apiBase}/tracing/runtimes/...` | P2 | Nenhuma ação imediata | AG-5 |
| `/my-issues` | Sim | vazia/placeholder | `// Simulando a API real devolvendo array vazio ... setIssues([]);` | P1 | Desenvolver API `/api/issues/my` no backend | AG-6 |
| `/observability` | Sim | consome-API-real | `fetch(\`\${apiBase}/health/ready\`)` | P2 | Nenhuma ação imediata | AG-5 |
| `/projects` | Sim | consome-API-real | `const response = await fetch(\`\${apiBase}/projects\`...` | P2 | Nenhuma ação imediata | AG-2 |
| `/seats` | Sim | consome-API-real | `const response = await fetch(\`\${API_URL}\${path}\`...` | P2 | Nenhuma ação imediata | AG-4 |
| `/sessions` | Sim | consome-API-real | `const response = await fetch(\`\${API_URL}/sessions/device-login\`...` | P2 | Nenhuma ação imediata | AG-4 |
| `/settings` | Sim | vazia/placeholder | `// Simulate API fetch delay ... setTimeout(() => setLoading(false), 400);` | P1 | Desenvolver API de configurações e integrar | AG-6 |
| `/squad-builder` | Sim | consome-API-real | `api.getTopology(SQUAD_ID)` (internamente usa fetch) | P2 | Nenhuma ação imediata | AG-3 |
