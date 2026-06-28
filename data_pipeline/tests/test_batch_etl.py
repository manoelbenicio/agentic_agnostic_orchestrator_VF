from __future__ import annotations

import json
from pathlib import Path

from data_pipeline import BatchETLConfig, run_batch_etl


def test_batch_etl_loads_csv_to_date_partitions(tmp_path: Path) -> None:
    source = tmp_path / "events.csv"
    source.write_text(
        "\n".join(
            [
                "event_id,event_type,occurred_at,tenant_id,project_id,amount_usd,payload",
                'evt-1,TOKEN_COST,2026-06-27T10:00:00Z,tenant-a,proj-a,1.25,"{""model"":""glm""}"',
                'evt-2,SEAT_COST,2026-06-28T11:00:00Z,tenant-a,proj-b,2.50,"{""seat"":""s1""}"',
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = run_batch_etl(BatchETLConfig(input_path=source, output_dir=tmp_path / "lake", run_id="test-run"))

    assert result.records_read == 2
    assert result.records_written == 2
    assert result.records_rejected == 0
    assert result.partitions == {"2026-06-27": 1, "2026-06-28": 1}

    partition = tmp_path / "lake" / "aop_events" / "run_id=test-run" / "partition_date=2026-06-27" / "events.jsonl"
    record = json.loads(partition.read_text(encoding="utf-8").splitlines()[0])
    assert record["event_type"] == "token_cost"
    assert record["event_hash"]
    assert record["payload"] == {"model": "glm"}


def test_batch_etl_writes_rejections_and_manifest(tmp_path: Path) -> None:
    source = tmp_path / "events.jsonl"
    source.write_text(
        "\n".join(
            [
                json.dumps({"event_id": "evt-1", "event_type": "task_done", "occurred_at": "2026-06-27T10:00:00Z"}),
                json.dumps({"event_id": "", "event_type": "task_done", "occurred_at": "2026-06-27T10:00:00Z"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = run_batch_etl(BatchETLConfig(input_path=source, output_dir=tmp_path / "lake", run_id="reject-run"))

    assert result.records_read == 2
    assert result.records_written == 1
    assert result.records_rejected == 1
    assert result.rejected_path is not None
    assert "missing required fields: event_id" in Path(result.rejected_path).read_text(encoding="utf-8")

    manifest = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
    assert manifest["run_id"] == "reject-run"
    assert manifest["records_rejected"] == 1
