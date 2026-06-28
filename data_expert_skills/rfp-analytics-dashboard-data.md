# RFP Analytics Dashboard — Data Expert

## Role
Expert agent that maps RFP-Codex pipeline outputs to dashboard components, enforces traceability governance, and guides data loading for the Executive Dashboard.

---

## 1. Project Source Paths (Source of Truth)

| Priority | Path | Content |
|----------|------|---------|
| **1 — OUTPUTS** | `D:\VMs\Projetos\BPO\RFP-Codex-Project\OUTPUTS\` | Consolidated final artifacts (read first) |
| **2 — raw_extracts** | `D:\VMs\Projetos\BPO\RFP-Codex-Project\OUTPUTS\raw_extracts\` | 65 files: per-document `.json` + `.txt` extracts + `manifest.json` |
| **3 — Contract/Rules** | `D:\VMs\Projetos\BPO\RFP-Codex-Project\AGENTS.md` | Durable execution contract |
| **3 — Contract/Rules** | `D:\VMs\Projetos\BPO\RFP-Codex-Project\ANTIGRAVITY_STITCH_OUTPUT_CONTRACT_PTBR.md` | Antigravity + Stitch output contract |
| **3 — Contract/Rules** | `D:\VMs\Projetos\BPO\RFP-Codex-Project\MASTER_PROMPT_RFP_DILIGENCE_ORCHESTRATOR_V2.3_CODEX_OFFICIAL_PTBR.md` | Task prompt |
| **4 — Templates** | `D:\VMs\Projetos\BPO\RFP-Codex-Project\TEMPLATES\TEMPLATES\` | Reference templates |

---

## 2. Governance Rules (from AGENTS.md)

### Princípio Zero — Never Lose Data
- Preserve all raw extracted content and provenance
- **Never invent facts** — if data is missing, mark `A_VALIDAR`
- If not applicable, use `NOT_APPLICABLE` with short justification
- Never hide extraction failures or document conflicts

### Anti-Hallucination Rule (Maximum)
**No data** may appear in any dashboard component (KPI, score, risk card, recommendation, insight, highlight, lowlight) without simultaneously having:
1. Traceable origin (`source_file`)
2. Source reference (`source_ref` — page/line/cell/tab/section)
3. `traceability_id`
4. `evidence_id` when available

If exact reference is unavailable due to parser limitations:
- Record best available reference (`section`, `sheet`, `table`, `range`, `page_estimate`)
- Mark reference granularity
- **Never fake precision**

### Executive Citation Format
Every material assertion must carry source metadata:
```
Fonte: <NOME_DO_ARQUIVO> | Ref: <PÁGINA|LINHA|CÉLULA|ABA|SEÇÃO>
```

### Material Document Classes (cannot remain silently unresolved)
- `CORE_RFP`, `LEGAL_CONTRACTUAL`, `COMMERCIALS_PRICING`, `WORKLOAD_VOLUME`, `TECHNICAL_ANNEX`

### Language
- All user-facing content in **pt-BR**
- Technical terms may remain in EN when appropriate

---

## 3. Complete File Catalog — OUTPUTS Directory

### 3.1. JSON Artifacts (7 files — Dashboard Primary Feed)

| File | Size | Dashboard Role |
|------|------|----------------|
| **`EXECUTIVE_DASHBOARD_DATA_PTBR.json`** | 20KB | **PRIMARY DATA SOURCE** — single JSON with all 10 data sections |
| `EXECUTIVE_HTML_PAYLOAD_PTBR.json` | 18KB | Pre-composed HTML component payloads |
| `EXECUTIVE_VISUALIZATION_SCHEMA_PTBR.json` | 6KB | 10 component specs with interaction models |
| `EXECUTIVE_UI_COPY_PTBR.json` | 4KB | All UI strings, labels, hints, disclaimers in pt-BR |
| `EXECUTIVE_FILTERS_SCHEMA_PTBR.json` | 3KB | 8 filter definitions with affected components |
| `SOURCE_TRACEABILITY_INDEX_PTBR.json` | 16KB | 32 traceability entries linking insights → source docs |
| `0_RFP_TEMPLATE_with_index_v2.1_STRICT_FILLED.json` | 41KB | Full RFP template filled with extracted data |

### 3.2. CSV Artifacts (12 files — Structured Pack Outputs)

| File | Rows | Dashboard Section |
|------|------|-------------------|
| `9_Go_No_Go_Scorecard_FILLED.csv` | 10 | Scorecard radar/heatmap |
| `10_Executive_Summary_FILLED.csv` | 4 | Hero section, recommendation |
| `11_Customer_Questions_Pack_FILLED.csv` | 11 | Questions table |
| `3_Evidence_Log_FILLED.csv` | ~20 | Traceability drilldown |
| `4_File_Inventory_FILLED.csv` | ~35 | Document coverage bar |
| `5_QA_Log_FILLED.csv` | ~10 | Quality gates, blockers source |
| `6_RTM_Traceability_FILLED.csv` | ~15 | Requirements trace |
| `7_Technology_Catalog_FILLED.csv` | 6 | Technology stack chips |
| `8_CH168_Validation_Checklist_FILLED.csv` | ~12 | Validation gates |
| `12_Reading_Report_FILLED.csv` | ~35 | Extraction status per file |
| `13_Practices_Catalog_FILLED.csv` | 5 | Practices component |
| `14_Decision_Log_FILLED.csv` | ~3 | Governance/decision panel |

### 3.3. Other Outputs

| File | Format | Usage |
|------|--------|-------|
| `GO_NO_GO_Report_FINAL.docx` | DOCX (37KB) | Formal report download |
| `GO_NO_GO_Report_FINAL.pdf` | PDF (2KB) | Alternative download |
| `Executive_Summary_Table.xlsx` | XLSX (8KB) | Exportable summary table |

---

## 4. EXECUTIVE_DASHBOARD_DATA_PTBR.json — Internal Structure

This is the **single file** the dashboard loads. It contains these top-level keys:

### `kpis` — 10 Hero KPIs
| KPI ID | Label | Value | Unit |
|--------|-------|-------|------|
| KPI-001 | Recomendação | GO_CONDITIONAL | status |
| KPI-002 | Score Ponderado | 3.08 | 0-5 |
| KPI-003 | Confiança da Avaliação | 0.65 | 0-1 |
| KPI-004 | Volume Total (48 meses) | 3,781,210 | unidades de serviço |
| KPI-005 | Valor Base Lote 1 | R$ 29,899,851.82 | BRL |
| KPI-006 | Blockers P0 | 4 | quantidade |
| KPI-007 | Perguntas em Aberto | 11 | quantidade |
| KPI-008 | Cobertura de Extração | 32/35 | documentos |
| KPI-009 | Quality Gates | 9/10 | gates |
| KPI-010 | Status de Decisão | PENDING | status |

### `scorecard_flat` — 10 Weighted Dimensions
Dimensions: Strategic Fit, Scope Clarity, Delivery Feasibility, Commercial Attractiveness, Legal/Contract Risk, Financial Exposure, Pricing Data Sufficiency, Competitive Position, Timeline Realism, Assessment Confidence.
- Total weighted score: **3.08/5.00**
- Lowest: Legal/Contract Risk (score=2, weighted=0.24)
- Each entry has `traceability_id` and `source_file`

### `risk_register_flat` — 6 Material Risks
- 5 × P0: Fator K fixo, sem faturamento mínimo, multa mobilização, carga trabalhista, LGPD
- 1 × P1: Retrabalho acima de 2%
- Categories: Comercial, Operacional/Financeiro, Legal/Compliance, Compliance, Operacional
- Each has `impacto`, `mitigacao`, `traceability_id`, `source_file`, `source_ref`

### `blockers_flat` — 5 P0 Blockers
| ID | Title | Owner | Status |
|----|-------|-------|--------|
| B-001 | Prazo de submissão não identificado | PMO | OPEN |
| B-002 | Modelo de custo interno não validado | Finance | OPEN |
| B-003 | Disponibilidade de CAT de 3 anos não confirmada | Legal/Commercial | OPEN |
| B-004 | Landscape competitivo sem visibilidade | Strategy | OPEN |
| B-005 | Valor base consolidado do Lote 2 a validar | Commercial | OPEN |

### `questions_flat` — 11 Customer Questions
- 5 × P0 (Q-001 to Q-005): Timeline, Commercial, Qualification, Mobilization
- 6 × P1 (Q-006 to Q-012): Competitive, Delivery, HR, Volumes, Legal, Scope
- Each has `owner`, `status=OPEN`, `traceability_id`

### `technology_flat` — 6 Mandatory Technologies
Eletromapa GIS, PROJ3/Kaffa, SAP, OMS, BERNHOEFT/ContractWeb, VPN Site-to-Site

### `practices_flat` — 5 Required Practices
GIS Data Management, Data Quality/BDGD Compliance, Workforce Management/HR, HSE, IT Infrastructure

### `sizing_flat` — 2 Lot Scenarios (directional)
| Lot | Volume 48mo | Monthly Avg | FTE Range |
|-----|-------------|-------------|-----------|
| Lote 1 (GO/AL/RS) | 1,718,220 | 35,796 | 60-80 |
| Lote 2 (PA/MA/PI/AP) | 2,062,990 | 42,979 | 70-100 |

### `timeline_flat` — 3 Key Events
All with `status=A_VALIDAR` or `PENDING`, all `criticidade=P0`

### `recommendation_flat` — Final Recommendation
- **GO_CONDITIONAL** | Score: 3.08 | Confidence: 0.65
- 4 Conditions: CAT confirmation, internal cost model, submission deadline, competitive mapping
- Decision Authority: Diretoria_Prática, Diretoria_Mercado
- Status: PENDING

---

## 5. Visualization Schema — 10 Dashboard Components

From `EXECUTIVE_VISUALIZATION_SCHEMA_PTBR.json`:

| Component ID | Type | Title (pt-BR) | Data Source Key |
|--------------|------|---------------|-----------------|
| `hero_recommendation` | hero_card | Recomendação Executiva | `recommendation_flat` |
| `scorecard_matrix` | weighted_table_heat | Scorecard Ponderado por Dimensão | `scorecard_flat` |
| `risk_heatmap` | risk_matrix | Mapa de Riscos Materiais | `risk_register_flat` |
| `cards_blockers` | priority_cards | Blockers P0 | `blockers_flat` |
| `questions_table` | interactive_table | Perguntas ao Cliente | `questions_flat` |
| `technology_stack` | chip_table | Stack Tecnológica Obrigatória | `technology_flat` |
| `sizing_panel` | scenario_cards | Sizing Direcional por Lote | `sizing_flat` |
| `document_coverage` | kpi_bar | Cobertura de Leitura Documental | `document_inventory_flat` |
| `timeline_gate` | milestone_list | Linha Crítica de Decisão | `timeline_flat` |
| `governance_panel` | governance_card | Governança da Deliberação | `recommendation_flat` |

### Source Visibility Rules
- **Every material component** must show `source_file`, `source_ref`, `traceability_id`
- Risk material without source **must not render**
- P0 milestones without source **must not render**
- Hover on any score/insight shows source + confidence

---

## 6. Filter Schema — 8 Interactive Filters

| Filter ID | Label (pt-BR) | Type | Affects |
|-----------|---------------|------|---------|
| `criticidade` | Criticidade | enum multi | risk, blockers, questions, timeline |
| `dominio` | Domínio | enum multi | risk, scorecard |
| `pratica_torre` | Prática/Torre | enum multi | tech, sizing |
| `documento_fonte` | Documento Fonte | searchable enum | scorecard, risk, blockers, questions, tech, docs |
| `tecnologia_vendor` | Tecnologia/Vendor | enum multi | tech, questions |
| `status_item` | Status | enum multi | blockers, questions, timeline, governance |
| `blocker_flag` | Blocker / Não Blocker | boolean | blockers, risk, hero |
| `fase_workstream` | Fase/Workstream | enum multi | questions, timeline, risk |

---

## 7. UI Copy Reference

All UI strings are in `EXECUTIVE_UI_COPY_PTBR.json`:
- `titulos` — Section headings
- `subtitulos` — Section descriptions
- `labels` — Field labels (Recomendação, Score Ponderado, Confiança, etc.)
- `hints` — Interaction hints (hover, click, filter)
- `empty_states` — Empty state messages
- `mensagens_warning` — Warning banners (blockers P0, confidence, A_VALIDAR, extraction failures)
- `explicacoes_score` — Score explanations (scale, weights, GO_CONDITIONAL rule)
- `disclaimers_de_fonte` — Source disclaimers (traceability, sizing caveat)
- `mensagens_de_filtro` — Filter feedback messages

---

## 8. Raw Extracts Reference

`OUTPUTS/raw_extracts/` contains **65 files**:
- 32 documents × 2 formats (`.json` structured + `.txt` plain text)
- Plus `manifest.json` linking F-IDs to original filenames
- File naming: `F-NNN__<original_filename>.<ext>.json|.txt`
- Example: `F-029__MINUTA PADRÃO - BDGD 08012026VF.pdf.json` (136KB)

**Use raw_extracts for:**
- Validating material assertions from OUTPUTS
- Verifying `source_ref` (page, section, clause references)
- Deep-diving into specific document content
- Never as primary data source — always start from OUTPUTS

---

## 9. Data Loading Pattern for Dashboard Build

```javascript
// 1. Load primary consolidated data
const dashData = await fetch('./OUTPUTS/EXECUTIVE_DASHBOARD_DATA_PTBR.json').then(r => r.json());

// 2. Load UI strings
const uiCopy = await fetch('./OUTPUTS/EXECUTIVE_UI_COPY_PTBR.json').then(r => r.json());

// 3. Load visualization schema (component specs)
const vizSchema = await fetch('./OUTPUTS/EXECUTIVE_VISUALIZATION_SCHEMA_PTBR.json').then(r => r.json());

// 4. Load filter definitions
const filters = await fetch('./OUTPUTS/EXECUTIVE_FILTERS_SCHEMA_PTBR.json').then(r => r.json());

// 5. Load traceability index (for drilldown)
const traceIndex = await fetch('./OUTPUTS/SOURCE_TRACEABILITY_INDEX_PTBR.json').then(r => r.json());

// Access data sections:
dashData.kpis              // 10 hero KPIs
dashData.scorecard_flat    // 10 weighted dimensions
dashData.risk_register_flat // 6 risks
dashData.blockers_flat     // 5 blockers
dashData.questions_flat    // 11 questions
dashData.technology_flat   // 6 technologies
dashData.practices_flat    // 5 practices
dashData.sizing_flat       // 2 lot scenarios
dashData.timeline_flat     // 3 timeline events
dashData.recommendation_flat // 1 recommendation
```

---

## 10. Stitch MCP Consumption Order

Per `ANTIGRAVITY_STITCH_OUTPUT_CONTRACT_PTBR.md`:
1. `EXECUTIVE_HTML_PAYLOAD_PTBR.json`
2. `EXECUTIVE_DASHBOARD_DATA_PTBR.json`
3. `EXECUTIVE_UI_COPY_PTBR.json`
4. `EXECUTIVE_VISUALIZATION_SCHEMA_PTBR.json`
5. `EXECUTIVE_FILTERS_SCHEMA_PTBR.json`
6. `SOURCE_TRACEABILITY_INDEX_PTBR.json`

**Fallback**: If Stitch MCP is unavailable, Antigravity renders the page as standalone HTML using the same artifacts. Never lose structure, text, or traceability.
