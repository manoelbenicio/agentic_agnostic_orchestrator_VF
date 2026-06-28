"""Local batch ETL pipeline for AOP analytical events."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REQUIRED_FIELDS = ("event_id", "event_type", "occurred_at")


@dataclass(frozen=True, slots=True)
class BatchETLConfig:
    """Filesystem-backed ETL inputs and outputs."""

    input_path: Path
    output_dir: Path
    dataset: str = "aop_events"
    run_id: str | None = None


@dataclass(frozen=True, slots=True)
class BatchETLResult:
    """Summary and artifact paths for one batch ETL run."""

    run_id: str
    dataset: str
    input_path: str
    output_dir: str
    records_read: int
    records_written: int
    records_rejected: int
    partitions: dict[str, int]
    manifest_path: str
    rejected_path: str | None


def run_batch_etl(config: BatchETLConfig) -> BatchETLResult:
    """Extract records from CSV/JSONL, transform them, and load JSONL partitions."""

    input_path = config.input_path
    if not input_path.exists():
        raise FileNotFoundError(input_path)
    if input_path.suffix.lower() not in {".csv", ".jsonl", ".ndjson"}:
        raise ValueError(f"unsupported input format: {input_path.suffix}")

    run_id = config.run_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output_dir = config.output_dir / config.dataset / f"run_id={run_id}"
    output_dir.mkdir(parents=True, exist_ok=True)

    records_read = 0
    records_written = 0
    rejected: list[dict[str, Any]] = []
    partitions: dict[str, int] = {}
    partition_files: dict[str, Any] = {}

    try:
        for line_number, raw_record in enumerate(_read_records(input_path), start=1):
            records_read += 1
            try:
                record = _normalize_record(raw_record, source=input_path.name, line_number=line_number)
            except ValueError as exc:
                rejected.append({"line_number": line_number, "error": str(exc), "record": raw_record})
                continue

            partition = record["partition_date"]
            handle = partition_files.get(partition)
            if handle is None:
                partition_path = output_dir / f"partition_date={partition}" / "events.jsonl"
                partition_path.parent.mkdir(parents=True, exist_ok=True)
                handle = partition_path.open("a", encoding="utf-8")
                partition_files[partition] = handle
            handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
            records_written += 1
            partitions[partition] = partitions.get(partition, 0) + 1
    finally:
        for handle in partition_files.values():
            handle.close()

    rejected_path = None
    if rejected:
        rejected_file = output_dir / "_rejected.jsonl"
        with rejected_file.open("w", encoding="utf-8") as handle:
            for item in rejected:
                handle.write(json.dumps(item, sort_keys=True, default=str, separators=(",", ":")) + "\n")
        rejected_path = str(rejected_file)

    result = BatchETLResult(
        run_id=run_id,
        dataset=config.dataset,
        input_path=str(input_path),
        output_dir=str(output_dir),
        records_read=records_read,
        records_written=records_written,
        records_rejected=len(rejected),
        partitions=dict(sorted(partitions.items())),
        manifest_path=str(output_dir / "_manifest.json"),
        rejected_path=rejected_path,
    )
    _write_manifest(result)
    return result


def _read_records(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8") as handle:
            return [dict(row) for row in csv.DictReader(handle)]
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                item = json.loads(line)
                if not isinstance(item, dict):
                    raise ValueError("JSONL records must be objects")
                records.append(item)
    return records


def _normalize_record(raw_record: dict[str, Any], *, source: str, line_number: int) -> dict[str, Any]:
    missing = [field for field in REQUIRED_FIELDS if not str(raw_record.get(field, "")).strip()]
    if missing:
        raise ValueError(f"missing required fields: {', '.join(missing)}")

    occurred_at = _parse_datetime(str(raw_record["occurred_at"]))
    event_id = str(raw_record["event_id"]).strip()
    tenant_id = str(raw_record.get("tenant_id") or "default").strip()
    project_id = str(raw_record.get("project_id") or "unknown").strip()
    event_type = str(raw_record["event_type"]).strip().lower()
    payload = _payload(raw_record.get("payload"))
    amount_usd = _optional_float(raw_record.get("amount_usd"))

    natural_key = f"{tenant_id}:{project_id}:{event_id}:{occurred_at.isoformat()}"
    return {
        "event_id": event_id,
        "event_hash": hashlib.sha256(natural_key.encode("utf-8")).hexdigest(),
        "event_type": event_type,
        "tenant_id": tenant_id,
        "project_id": project_id,
        "occurred_at": occurred_at.isoformat().replace("+00:00", "Z"),
        "partition_date": occurred_at.date().isoformat(),
        "amount_usd": amount_usd,
        "payload": payload,
        "source_file": source,
        "source_line": line_number,
        "loaded_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }


def _parse_datetime(value: str) -> datetime:
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"invalid occurred_at: {value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _payload(value: Any) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("payload must be a JSON object")


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _write_manifest(result: BatchETLResult) -> None:
    manifest_path = Path(result.manifest_path)
    manifest_path.write_text(json.dumps(asdict(result), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the AOP batch ETL pipeline")
    parser.add_argument("--input", required=True, type=Path, help="CSV, JSONL, or NDJSON source file")
    parser.add_argument("--output-dir", required=True, type=Path, help="Data lake output directory")
    parser.add_argument("--dataset", default="aop_events", help="Dataset name under the output directory")
    parser.add_argument("--run-id", default=None, help="Stable run id for deterministic backfills")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    result = run_batch_etl(
        BatchETLConfig(
            input_path=args.input,
            output_dir=args.output_dir,
            dataset=args.dataset,
            run_id=args.run_id,
        )
    )
    print(json.dumps(asdict(result), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
