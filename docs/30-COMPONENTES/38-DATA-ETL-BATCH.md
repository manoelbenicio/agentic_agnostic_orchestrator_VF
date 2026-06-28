# DATA - ETL Pipeline Batch

O pipeline batch da Fase 7 vive em `data_pipeline/batch_etl.py` e executa uma carga local deterministica para eventos analiticos da AOP.

## Contrato de entrada

Formatos aceitos:

- CSV (`.csv`)
- JSON Lines (`.jsonl` ou `.ndjson`)

Campos obrigatorios:

- `event_id`
- `event_type`
- `occurred_at`

Campos opcionais normalizados:

- `tenant_id` (`default` quando ausente)
- `project_id` (`unknown` quando ausente)
- `amount_usd`
- `payload` como objeto JSON

## Saida

A carga grava JSONL particionado por data:

```text
<output>/<dataset>/run_id=<run-id>/partition_date=YYYY-MM-DD/events.jsonl
```

Cada registro recebe:

- `event_hash` SHA-256 deterministico para deduplicacao downstream
- `partition_date` derivada de `occurred_at`
- `loaded_at`
- `source_file` e `source_line`

Registros invalidos sao enviados para `_rejected.jsonl`. Todo run gera `_manifest.json` com contadores, particoes e caminhos dos artefatos.

## Execucao

```bash
PYTHONPATH=. python -m data_pipeline.batch_etl \
  --input data_pipeline/example_events.csv \
  --output-dir /tmp/aop-data-lake \
  --dataset aop_events \
  --run-id backfill-20260627
```

## Validacao

```bash
PYTHONPATH=. pytest -q data_pipeline/tests
```
