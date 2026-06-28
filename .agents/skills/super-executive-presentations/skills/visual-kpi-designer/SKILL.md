---
name: visual-kpi-designer
description: "Designer especialista em KPIs visuais premium para apresentações executivas PPTX. Gera instruções e código python-pptx para componentes de dashboard Fortune 500: hero KPIs, gauges, progress bars, status badges, risk matrices, data tables — usando o design system existente (COL palette, rect, pill, metric, progress, node helpers)."
risk: safe
source: custom-elite
date_added: '2026-06-23'
author: elite-squad-charlie
tags:
  - kpi
  - visual-design
  - pptx
  - python-pptx
  - premium
  - executive
  - fortune500
tools:
  - antigravity
  - claude-code
  - cursor
  - gemini-cli
  - codex-cli
---

# VISUAL KPI DESIGNER — Componentes Premium PPTX v2.0

## Overview

Você é um **Senior Visual Designer** especializado em componentes de KPI para apresentações executivas PowerPoint. Cada componente que você cria usa o **design system python-pptx** já existente no projeto, gerando código Python production-ready que roda diretamente com `build_dn_ai_options.py`.

## When to Use This Skill

- Quando precisa criar componentes visuais de KPI para slides PPTX
- Quando precisa gerar código python-pptx usando o design system do projeto
- Quando precisa de componentes como progress bars, metrics, pills, nodes, status badges
- Quando precisa que o visual passe o "Boardroom Test"

## Do Not Use This Skill When

- Para criar o roteiro narrativo (use `ppt-narrative-architect`)
- Para gerar o conteúdo textual (use `executive-status-storyteller`)
- Para HTML/web dashboards (não é o foco — PPTX é prioridade)

---

## Design System Existente — Referência Obrigatória

### Paleta de Cores (`COL`)

O projeto já possui uma paleta profissional definida em `build_dn_ai_options.py`:

```python
COL = {
    # ═══ 12 CANONICAL SWATCHES — Official Indra DSS v3.0 ═══
    # Source: C:\Users\mbenicios\Downloads\UI_UX\indra_design_system\styles.css
    # RULE: NO SUBSTITUTION, NO APPROXIMATION
    "deep":      RGBColor(0x00, 0x2B, 0x3A),  # --indra-deep (primary bg)
    "dark":      RGBColor(0x00, 0x3E, 0x50),  # --indra-dark (secondary bg)
    "primary":   RGBColor(0x06, 0x59, 0x6E),  # --indra-primary
    "secondary": RGBColor(0x34, 0x66, 0x79),  # --indra-secondary
    "cyan":      RGBColor(0x00, 0xB0, 0xBD),  # --indra-cyan ★ (hero accent)
    "teal":      RGBColor(0x3F, 0x96, 0xAE),  # --indra-teal
    "light":     RGBColor(0x7A, 0x9C, 0xAE),  # --indra-light
    "blue_gray": RGBColor(0xB3, 0xC1, 0xDA),  # --indra-blue-gray
    "sky":       RGBColor(0xBA, 0xDF, 0xF3),  # --indra-sky
    "warm":      RGBColor(0xB0, 0xB4, 0xBD),  # --indra-warm-gray
    "off":       RGBColor(0xE8, 0xE8, 0xE1),  # Extended warm off-white
    "off2":      RGBColor(0xF2, 0xF5, 0xF6),  # --indra-off-white
    "white":     RGBColor(0xFF, 0xFF, 0xFF),  # White
    "ink":       RGBColor(0x00, 0x47, 0x5A),  # Dark text on light bg
    "gray":      RGBColor(0x65, 0x65, 0x5F),  # Muted text
    "line":      RGBColor(0xC7, 0xCB, 0xC5),  # Borders on light bg
    # ═══ STATUS — Official Indra DSS v3.0 ═══
    "green":     RGBColor(0x27, 0xAE, 0x60),  # --indra-success
    "amber":     RGBColor(0xFF, 0x98, 0x00),  # --indra-warning
    "red":       RGBColor(0xE9, 0x1E, 0x63),  # --indra-error
    "gold":      RGBColor(0xFF, 0xC1, 0x07),  # --indra-gold
}
```

### Uso Semântico das Cores

| Significado | Light Mode | Dark Mode |
|-------------|-----------|-----------|
| Background | `COL["off"]` / `COL["off2"]` | `COL["deep"]` / `COL["dark"]` |
| Texto principal | `COL["ink"]` | `COL["white"]` / `COL["off2"]` |
| Texto secundário | `COL["gray"]` | `COL["sky"]` |
| Accent/destaque | `COL["cyan"]` | `COL["cyan"]` |
| Positivo/concluído | `COL["green"]` | `COL["green"]` |
| Atenção/em andamento | `COL["amber"]` | `COL["amber"]` |
| Crítico/bloqueado | `COL["red"]` | `COL["red"]` |
| Bordas/linhas | `COL["line"]` | `COL["teal"]` |

---

## Helper Functions Disponíveis

### NUNCA recrie estas funções — importe de `build_dn_ai_options.py`:

```python
from build_dn_ai_options import (
    ROOT, TEMPLATE, COL,
    clear_slide,    # Limpa todos os shapes de um slide
    bg,             # Pinta o background do slide
    title,          # Adiciona título padrão "DN [sufixo]"
    footer,         # Adiciona footer com branding
    rect,           # Retângulo (com ou sem rounded corners)
    add_txt,        # Texto com posição, tamanho, cor, bold, alinhamento
    line,           # Configura borda de shape
    fill,           # Configura preenchimento de shape
    connector,      # Linha conectora entre pontos
    node,           # Círculo com label (para grafos/redes)
    pill,           # Badge arredondado com texto
    progress,       # Barra de progresso
    metric,         # Card de KPI com valor + label + accent color
    subtle_circuit, # Decoração de fundo (linhas de circuito)
)
```

### Assinaturas Essenciais

```python
# Background
bg(slide, color=COL["off"])  # Light mode
bg(slide, COL["deep"])       # Dark mode

# Texto (unidade: Inches)
add_txt(slide, text, x, y, w, h, size=18, color=COL["ink"],
        bold=False, align=PP_ALIGN.LEFT, font="Aptos", name=None)

# Retângulo
rect(slide, x, y, w, h, color, outline=None, radius=False,
     transparency=None, name=None)

# Pill badge
pill(slide, text, x, y, w, color=COL["primary"],
     text_color=COL["white"], size=10, name=None)

# Metric card (KPI)
metric(slide, value, label, x, y, w, h, accent=COL["cyan"],
       dark=False, name=None)

# Progress bar
progress(slide, x, y, w, pct, color=COL["cyan"],
         bg_color=COL["line"], h=0.09)

# Node (círculo com label)
node(slide, label, x, y, d=0.48, color=COL["primary"],
     text_color=COL["white"], size=11, name=None)
```

---

## Componentes Premium (Construídos com Helpers)

### 1. KPI Strip (Linha de Métricas)

```python
def kpi_strip(slide, metrics, x, y, dark=False):
    """
    metrics: list of (value, label, accent_color) tuples
    Renderiza uma faixa horizontal de KPI cards.
    """
    card_w = 1.8
    gap = 0.15
    for i, (value, label, accent) in enumerate(metrics):
        metric(slide, value, label,
               x + i * (card_w + gap), y,
               card_w, 0.78, accent, dark=dark)
```

**Exemplo de uso:**
```python
kpi_strip(slide, [
    ("78%", "progresso geral", COL["cyan"]),
    ("R$14.2M", "budget executado", COL["green"]),
    ("42 pts", "velocity sprint", COL["primary"]),
    ("1.2%", "defect rate", COL["teal"]),
], x=0.5, y=1.3, dark=True)
```

### 2. Status Badge Row

```python
def status_badges(slide, items, x, y, dark=False):
    """
    items: list of (label, status) where status = 'green'|'amber'|'red'
    """
    colors = {"green": COL["green"], "amber": COL["amber"], "red": COL["red"]}
    badge_w = 1.4
    for i, (label, status) in enumerate(items):
        xi = x + i * (badge_w + 0.2)
        pill(slide, f"● {label}", xi, y, badge_w,
             colors[status],
             COL["deep"] if status == "amber" else COL["white"], 9)
```

**Exemplo:**
```python
status_badges(slide, [
    ("Schedule", "green"),
    ("Budget", "green"),
    ("Quality", "green"),
    ("Risk", "amber"),
], x=3.5, y=0.8)
```

### 3. Executive Summary Card

```python
def exec_summary_card(slide, data, x, y, w, h, dark=False):
    """
    data: dict with keys: status, delivery, budget_used, budget_total,
          team, sprint, open_risks, decisions
    """
    bg_color = COL["dark"] if dark else COL["white"]
    text_color = COL["white"] if dark else COL["ink"]
    label_color = COL["sky"] if dark else COL["gray"]
    border = COL["teal"] if dark else COL["line"]

    rect(slide, x, y, w, h, bg_color, border, radius=True)
    add_txt(slide, "QUICK FACTS", x + 0.2, y + 0.15, w - 0.4, 0.2,
            11, COL["cyan"], True)

    rows = [
        ("Status", data["status"], COL["green"]),
        ("Delivery", data["delivery"], text_color),
        ("Budget", f'{data["budget_used"]} / {data["budget_total"]}', text_color),
        ("Team", data["team"], text_color),
        ("Sprint", data["sprint"], text_color),
        ("Open Risks", data["open_risks"], COL["amber"]),
        ("Decisions", data["decisions"], COL["amber"]),
    ]
    for i, (key, value, val_color) in enumerate(rows):
        row_y = y + 0.45 + i * 0.28
        add_txt(slide, key, x + 0.2, row_y, 1.5, 0.15, 10, label_color)
        add_txt(slide, str(value), x + w - 2.5, row_y, 2.2, 0.15,
                10, val_color, True, PP_ALIGN.RIGHT)
```

### 4. Risk Matrix Table

```python
def risk_table(slide, risks, x, y, w, dark=False):
    """
    risks: list of dicts with keys: priority, risk, impact, mitigation, owner, deadline
    """
    bg_color = COL["dark"] if dark else COL["white"]
    header_bg = COL["primary"] if dark else COL["warm"]
    text_color = COL["off2"] if dark else COL["ink"]
    border = COL["teal"] if dark else COL["line"]

    headers = ["Prio", "Risco", "Impacto", "Mitigação", "Dono", "Prazo"]
    col_ws = [0.6, w * 0.25, w * 0.2, w * 0.25, 0.8, 0.7]
    row_h = 0.38

    # Header
    xi = x
    for header, cw in zip(headers, col_ws):
        rect(slide, xi, y, cw, row_h, header_bg, border)
        add_txt(slide, header, xi + 0.05, y + 0.09, cw - 0.1, 0.12,
                8.5, COL["white"], True, PP_ALIGN.CENTER)
        xi += cw

    # Rows
    priority_colors = {"P1": COL["red"], "P2": COL["amber"], "P3": COL["cyan"]}
    for r, risk in enumerate(risks):
        ry = y + row_h + r * row_h
        row_bg = COL["off2"] if r % 2 == 0 else COL["off"]
        if dark:
            row_bg = COL["dark"] if r % 2 == 0 else RGBColor(0x00, 0x37, 0x46)

        xi = x
        for col_key, cw in zip(
            ["priority", "risk", "impact", "mitigation", "owner", "deadline"], col_ws
        ):
            rect(slide, xi, ry, cw, row_h, row_bg, border)
            val = risk[col_key]
            if col_key == "priority":
                pill(slide, val, xi + 0.08, ry + 0.07, 0.42,
                     priority_colors.get(val, COL["teal"]),
                     COL["white"], 7)
            else:
                add_txt(slide, str(val), xi + 0.05, ry + 0.09, cw - 0.1, 0.15,
                        8.5, text_color, False)
            xi += cw
```

### 5. Timeline / Roadmap

```python
def timeline_bar(slide, phases, x, y, w, dark=False):
    """
    phases: list of dicts: {name, date, status: 'done'|'current'|'upcoming'}
    """
    track_color = COL["primary"] if dark else COL["line"]
    rect(slide, x, y + 0.3, w, 0.08, track_color, radius=True)

    done_phases = sum(1 for p in phases if p["status"] == "done")
    total = len(phases)
    pct = (done_phases + 0.5) / total  # current phase at midpoint
    rect(slide, x, y + 0.3, w * pct, 0.08,
         COL["green"] if not dark else COL["cyan"], radius=True)

    spacing = w / (total - 1) if total > 1 else 0
    for i, phase in enumerate(phases):
        px = x + i * spacing
        color_map = {
            "done": COL["green"],
            "current": COL["cyan"],
            "upcoming": COL["warm"]
        }
        node(slide, "", px - 0.15, y + 0.15, 0.38,
             color_map[phase["status"]],
             COL["deep"] if phase["status"] != "done" else COL["white"], 8)
        add_txt(slide, phase["name"], px - 0.5, y + 0.6, 1.0, 0.2,
                9, COL["white"] if dark else COL["ink"], True, PP_ALIGN.CENTER)
        add_txt(slide, phase["date"], px - 0.5, y + 0.82, 1.0, 0.15,
                8, COL["sky"] if dark else COL["gray"], False, PP_ALIGN.CENTER)
```

### 6. Decision Action Items

```python
def decision_cards(slide, decisions, x, y, w, dark=False):
    """
    decisions: list of dicts: {text, deadline}
    """
    for i, d in enumerate(decisions):
        dy = y + i * 0.65
        rect(slide, x, dy, w, 0.55,
             COL["dark"] if dark else COL["white"],
             COL["amber"], radius=True)
        rect(slide, x, dy, 0.08, 0.55, COL["amber"])  # Left accent
        add_txt(slide, "⚡", x + 0.18, dy + 0.12, 0.3, 0.2, 14,
                COL["amber"])
        add_txt(slide, d["text"], x + 0.5, dy + 0.08, w - 0.7, 0.2,
                10.5, COL["white"] if dark else COL["ink"], True)
        add_txt(slide, f'Deadline: {d["deadline"]}', x + 0.5, dy + 0.32,
                w - 0.7, 0.15, 9, COL["amber"], True)
```

---

## Slide Canvas Reference

PowerPoint widescreen (16:9): **13.333" × 7.5"**

```
┌─────────────────────────────────────────────────────┐
│  0.38" margin                                       │ 0"
│  ┌──────────── TITLE BAR ────────────────────────┐  │ 0.35"
│  └───────────────────────────────────────────────┘  │ 0.90"
│  ┌──── KPI STRIP ────────────────────────────────┐  │ 1.10"
│  └───────────────────────────────────────────────┘  │ 2.00"
│  ┌───────────────────┐  ┌────────────────────────┐  │
│  │   PRIMARY CHART   │  │   SECONDARY PANEL      │  │ 2.20"
│  │   (7.5" wide)     │  │   (4.5" wide)          │  │
│  └───────────────────┘  └────────────────────────┘  │ 5.80"
│  ┌──── BOTTOM MESSAGE ───────────────────────────┐  │ 6.00"
│  └───────────────────────────────────────────────┘  │ 6.60"
│  FOOTER                                             │ 7.10"
└─────────────────────────────────────────────────────┘ 7.50"
     0"        3"        6"        9"       12"   13.33"
```

---

## Regras de Layout para PPTX

1. **Margens**: 0.38" laterais, 0.35" topo
2. **Grid**: Slide dividido em zonas (título, KPIs, conteúdo, footer)
3. **KPI cards**: máximo 5 por strip, mínimo 1.18" de largura
4. **Texto mínimo**: 8pt para labels, 10pt para body, 23pt+ para hero KPIs
5. **Font padrão**: Aptos (já definido no template)
6. **Espaçamento**: 0.15" gap entre cards, 0.3" entre seções
7. **Rounded corners**: `radius=True` nos rects de cards e panels
8. **Naming**: Use `name=` parameter para identificar shapes para animação

## Anti-Patterns PPTX

- ❌ Criar shapes sem importar os helpers — sempre use `rect()`, `pill()`, `metric()`
- ❌ Hard-code cores RGB — sempre use `COL["nome"]`
- ❌ Texto abaixo de 8pt
- ❌ Mais de 5 KPI cards no strip
- ❌ Elementos fora das margens (< 0.3" ou > 13.0")
- ❌ Shapes sem `name=` quando animação for necessária

## Related Skills

- `ppt-narrative-architect` — Define o roteiro narrativo
- `executive-status-storyteller` — Gera o conteúdo textual
- `slide-animation-director` — Adiciona animações PowerPoint nativas
- `fortune500-executive-dashboard` — Referência de design premium

## Limitations
- Use this skill only when the task clearly matches the scope described above.
- Do not treat the output as a substitute for environment-specific validation, testing, or expert review.
- Stop and ask for clarification if required inputs, permissions, safety boundaries, or success criteria are missing.
