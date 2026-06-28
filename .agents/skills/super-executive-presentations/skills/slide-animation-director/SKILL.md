---
name: slide-animation-director
description: "Diretor de animações PowerPoint nativas para apresentações executivas. Especialista em python-pptx XML manipulation para adicionar entrance animations (Fade, Float Up, Wipe), emphasis effects, exit animations, e sequenciamento profissional de animações em slides PPTX. Faz slides estáticos parecerem vivos e premium sem ser decorativo."
risk: safe
source: custom-elite
date_added: '2026-06-23'
author: elite-squad-charlie
tags:
  - animation
  - pptx
  - powerpoint
  - python-pptx
  - motion-design
  - executive
  - xml
tools:
  - antigravity
  - claude-code
  - cursor
  - gemini-cli
  - codex-cli
---

# SLIDE ANIMATION DIRECTOR — Animações PowerPoint Nativas v2.0

## Overview

Você é um **Motion Design Director** para apresentações executivas PowerPoint. Suas animações usam os **efeitos nativos do PowerPoint** aplicados via python-pptx XML manipulation — não CSS. Cada animação segue a regra de ouro: **"A melhor animação é a que o executivo não percebe conscientemente, mas subconscientemente aprecia."**

## When to Use This Skill

- Quando precisa adicionar animações de entrada a shapes em slides PPTX
- Quando precisa sequenciar a aparição de elementos (staggered reveal)
- Quando precisa de emphasis effects para destacar KPIs ou status
- Quando quer que a apresentação pareça "viva" sem ser distrativa

## Princípio: "Invisible Animation"

Em boardrooms C-Level, animações devem:
1. ✅ Revelar informação na sequência certa (guiar a narrativa)
2. ✅ Destacar o que é mais importante
3. ✅ Criar sensação de polish e qualidade premium
4. ❌ NUNCA ser distrativas ou infantis (sem bounces, spins, ou fly-ins exagerados)

---

## Como Animações Funcionam em python-pptx

python-pptx **não tem API nativa para animações**, mas podemos manipular o XML
diretamente no slide para adicionar efeitos. Cada slide tem um elemento `<p:timing>`
que contém a sequência de animações.

### Namespacing Necessário

```python
from pptx.oxml.ns import qn, nsmap
from lxml import etree
import copy

# Namespace map for animation XML
ANIM_NS = {
    'a': 'http://schemas.openxmlformats.org/drawingml/2006/main',
    'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    'p': 'http://schemas.openxmlformats.org/presentationml/2006/main',
}
```

---

## Animation Effects Aprovados para C-Level

### Efeitos PERMITIDOS (Premium)

| Efeito | PowerPoint Name | Preset ID | Quando Usar |
|--------|----------------|-----------|-------------|
| **Fade** | `anim_fade` | 10 | Entrada padrão para qualquer elemento |
| **Float Up** | `anim_floatUp` | 42 | Entrada de cards e KPIs (sutil) |
| **Wipe** | `anim_wipe` | 22 | Barras de progresso, timelines |
| **Appear** | `anim_appear` | 1 | Sequenciamento rápido (0ms) |
| **Grow/Shrink** | `emph_grow` | - | Emphasis em KPIs importantes |

### Efeitos PROIBIDOS (Unprofessional)

- ❌ Bounce, Spin, Swivel, Pinwheel
- ❌ Fly In (de qualquer direção)
- ❌ Checkerboard, Blinds, Random Bars
- ❌ Qualquer efeito 3D
- ❌ Sound effects de qualquer tipo

---

## Receitas de Animação

### 1. Fade In Sequencial (Staggered Reveal)

O padrão mais usado: elementos aparecem em sequência com delay entre eles.

```python
def add_fade_animation(slide, shape, delay_ms=0, duration_ms=500):
    """
    Adiciona efeito Fade ao shape com delay específico.
    delay_ms: quanto tempo esperar antes de iniciar (após click ou após anterior)
    duration_ms: duração do fade (500ms = premium, 300ms = rápido)
    """
    # Identificar o shape no spTree
    sp = shape._element
    sp_id = sp.attrib.get('id', sp.find(qn('p:cNvPr')).attrib.get('id', '2'))

    # Buscar ou criar o elemento de timing
    timing = slide._element.find(qn('p:timing'))
    if timing is None:
        timing_xml = f'''
        <p:timing xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
          <p:tnLst>
            <p:par>
              <p:cTn id="1" dur="indefinite" restart="never" nodeType="tmRoot">
                <p:childTnLst>
                  <p:seq concurrent="1" nextAc="seek">
                    <p:cTn id="2" dur="indefinite" nodeType="mainSeq">
                      <p:childTnLst/>
                    </p:cTn>
                    <p:prevCondLst>
                      <p:cond evt="onPrev" delay="0">
                        <p:tgtEl><p:sldTgt/></p:tgtEl>
                      </p:cond>
                    </p:prevCondLst>
                    <p:nextCondLst>
                      <p:cond evt="onNext" delay="0">
                        <p:tgtEl><p:sldTgt/></p:tgtEl>
                      </p:cond>
                    </p:nextCondLst>
                  </p:seq>
                </p:childTnLst>
              </p:cTn>
            </p:par>
          </p:tnLst>
        </p:timing>
        '''
        timing = etree.fromstring(timing_xml)
        slide._element.append(timing)

    # Nota: a manipulação XML completa é complexa.
    # Para produção, recomenda-se o approach de template:
    # 1. Criar um slide de referência com animações no PowerPoint
    # 2. Clonar a estrutura XML das animações para novos slides


def get_shape_id(shape):
    """Extrai o ID numérico do shape para referência em animações."""
    cNvPr = shape._element.find('.//' + qn('p:cNvPr'))
    if cNvPr is None:
        cNvPr = shape._element.find('.//' + qn('a:cNvPr'))
    if cNvPr is not None:
        return cNvPr.get('id')
    return None
```

### 2. Approach de Template (Recomendado para Produção)

O método mais confiável para animações complexas:

```python
def apply_animations_from_template(prs, template_slide_idx, target_slide):
    """
    Copia a estrutura de timing/animação de um slide template
    para o slide alvo. O template deve ter shapes com os mesmos
    nomes (name= parameter) que o slide alvo.
    
    Workflow:
    1. Crie um .pptx com as animações desejadas no PowerPoint
    2. Use este script para copiar as animações para slides gerados
    """
    template_slide = prs.slides[template_slide_idx]
    
    # Copiar timing element
    source_timing = template_slide._element.find(qn('p:timing'))
    if source_timing is not None:
        # Remover timing existente no target
        existing = target_slide._element.find(qn('p:timing'))
        if existing is not None:
            target_slide._element.remove(existing)
        
        # Copiar e adaptar
        new_timing = copy.deepcopy(source_timing)
        target_slide._element.append(new_timing)
```

### 3. Shape Naming Convention para Animações

**CRITICAL**: Para que animações funcionem, shapes DEVEM ter nomes consistentes.

```python
# Ao criar shapes, SEMPRE use o parameter name=
rect(slide, x, y, w, h, color, name="anim_card_1")
rect(slide, x, y, w, h, color, name="anim_card_2")
metric(slide, "42", "velocity", x, y, w, h, COL["cyan"], name="anim_kpi_1")
pill(slide, "ON TRACK", x, y, w, COL["green"], name="anim_badge_status")
```

**Convenção de nomes:**

| Prefixo | Uso | Exemplo |
|---------|-----|---------|
| `anim_card_N` | Cards/painéis que aparecem em sequência | `anim_card_1`, `anim_card_2` |
| `anim_kpi_N` | KPI metrics que contam | `anim_kpi_velocity` |
| `anim_badge_X` | Status badges | `anim_badge_status` |
| `anim_row_N` | Linhas de tabela | `anim_row_1`, `anim_row_2` |
| `anim_phase_X` | Fases de timeline | `anim_phase_discovery` |
| `anim_block_X` | Blocos de conteúdo | `anim_block_focus` |

---

## Sequenciamento Recomendado por Tipo de Slide

### Executive Summary (Ato 1: Hook)

```
Click 1 (ou Auto):
  1. Background + Title (instant) ————— 0ms
  2. Status Badge "ON TRACK" (fade) ——— 200ms delay
  3. Gauge / Hero KPI (fade + grow) ——— 400ms delay
  4. Health Strip (fade) ———————————— 600ms delay
  5. Quick Facts panel (fade) ————————— 800ms delay
```

### KPI Dashboard (Ato 5: Numbers)

```
Click 1:
  1. Title (instant) ———————————————— 0ms
Click 2 (ou after previous):
  2. KPI Card 1 (float up) ——————————— 0ms
  3. KPI Card 2 (float up) ——————————— 100ms delay
  4. KPI Card 3 (float up) ——————————— 200ms delay
  5. KPI Card 4 (float up) ——————————— 300ms delay
```

### Risks Table (Ato 4: Hard Truth)

```
Click 1:
  1. Title (instant) ———————————————— 0ms
  2. Table header (wipe) ———————————— 200ms delay
Click 2:
  3. Row 1 P1 risk (fade) ——————————— 0ms
  4. Row 2 P1 risk (fade) ——————————— 150ms delay
  5. Rows 3-6 P2/P3 (fade) ——————————— 300ms delay (together)
```

### Timeline (Ato 6: Path Forward)

```
Click 1:
  1. Timeline track (wipe left-to-right) — 0ms
  2. Phase 1 node done (appear) ————————— 200ms
  3. Phase 2 node done (appear) ————————— 400ms
  4. Phase 3 node current (fade + glow) — 600ms
  5. Phase 4 node upcoming (fade dim) ——— 800ms
```

---

## Timing Guidelines

| Contexto | Duração | Delay entre elementos |
|----------|---------|----------------------|
| Sequência rápida (KPIs, badges) | 300-500ms | 80-150ms |
| Reveal principal (gauge, hero) | 500-800ms | — |
| Table rows (staggered) | 300ms | 100-150ms |
| Timeline phases | 400ms | 200ms |
| Background elements | instant (0ms) | — |
| Emphasis (pulse, grow) | 500ms | — |

**Regra de ouro**: Toda a sequência de animação de um slide deve completar em **< 3 segundos**. O apresentador não deve esperar pela animação.

---

## Performance Guidelines para PPTX

1. **Máximo 15 animações por slide** — mais que isso torna o slide lento
2. **Evite animações em slides com > 30 shapes** — PowerPoint pode engasgar
3. **Teste em projetor real** — animações suaves no laptop podem ter lag no projetor
4. **Sempre tenha versão sem animação** — para PDF export ou fallback
5. **Use "After Previous" em vez de "On Click"** para sequências automáticas

## Best Practices

- Nome TODOS os shapes que serão animados com prefixo `anim_`
- Crie um slide template com animações no PowerPoint → copie via XML
- Teste a sequência completa no modo apresentação antes de entregar
- Forneça versão com E sem animações

## Related Skills

- `ppt-narrative-architect` — Define o roteiro narrativo e sequência
- `executive-status-storyteller` — Gera o conteúdo textual
- `visual-kpi-designer` — Cria os componentes visuais PPTX
- `css-animation-microinteraction-expert` — Referência de timing e easing (para HTML)

## Limitations
- python-pptx não tem API nativa de animações — requer XML manipulation
- Recomenda-se approach de template para animações complexas
- Teste sempre no PowerPoint nativo antes de entregar
