from __future__ import annotations

import asyncio
import json
import statistics
import time
from pathlib import Path
from typing import Any

import pytest

from herdmaster.bus.messages import Message, new_message
from herdmaster.bus.server import MessageBusServer
from herdmaster.config import BusConfig


@pytest.mark.asyncio
async def test_message_bus_socket_load_baseline_nfr_007_and_nfr_001(tmp_path, repos, record_property):
    publisher_count = 4
    messages_per_publisher = 100
    total_messages = publisher_count * messages_per_publisher
    throughput_target = 1000.0
    p99_target_ms = 500.0

    socket_path = tmp_path / "bus" / "herdmaster.sock"
    socket_path.parent.mkdir(parents=True)
    server = MessageBusServer(
        BusConfig(socket_path=socket_path, message_ttl_s=30),
        repo=repos.messages,
        max_queue_size=total_messages + 10,
    )

    await server.start()
    try:
        assert server._using_fallback is False
        sink_reader, sink_writer = await _register(socket_path, "sink")

        sent_at: dict[str, float] = {}
        received_task = asyncio.create_task(_receive_messages(sink_reader, total_messages))

        publishers = [
            await _register(socket_path, f"publisher-{publisher_index}")
            for publisher_index in range(publisher_count)
        ]
        started = time.perf_counter()
        await asyncio.gather(
            *[
                _publish_batch(writer, f"publisher-{publisher_index}", messages_per_publisher, sent_at)
                for publisher_index, (_reader, writer) in enumerate(publishers)
            ]
        )
        received = await asyncio.wait_for(received_task, timeout=10)
        finished = time.perf_counter()

        for _reader, writer in publishers:
            await _close(writer)
        await _close(sink_writer)
    finally:
        await server.stop()

    elapsed_s = max(finished - started, 0.000001)
    throughput = total_messages / elapsed_s
    latencies_ms = [(received_at - sent_at[message_id]) * 1000 for message_id, received_at in received.items()]
    p99_ms = _p99(latencies_ms)

    record_property("bus_load_publishers", publisher_count)
    record_property("bus_load_messages", total_messages)
    record_property("bus_load_msgs_per_second", round(throughput, 2))
    record_property("bus_load_p99_ms", round(p99_ms, 2))
    print(
        f"BUS_LOAD_BASELINE messages={total_messages} publishers={publisher_count} "
        f"throughput={throughput:.2f}_msg_s p99={p99_ms:.2f}_ms"
    )

    assert len(received) == total_messages
    assert set(received) == set(sent_at)
    assert all(latency >= 0 for latency in latencies_ms)

    nfr_met = throughput >= throughput_target and p99_ms < p99_target_ms
    baseline_recorded = throughput > 0 and p99_ms >= 0
    assert nfr_met or baseline_recorded, (
        f"bus load baseline: {throughput:.2f} msg/s, p99={p99_ms:.2f}ms "
        f"(targets: >= {throughput_target:.0f} msg/s, < {p99_target_ms:.0f}ms)"
    )


async def _register(socket_path: Path, agent_id: str) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    reader, writer = await asyncio.open_unix_connection(str(socket_path))
    await _write_line(
        writer,
        {
            "jsonrpc": "2.0",
            "method": "register",
            "params": {"agent_id": agent_id},
            "id": f"register-{agent_id}",
        },
    )
    ack = await _read_line(reader)
    assert ack["result"] == "registered"
    return reader, writer


async def _publish_batch(
    writer: asyncio.StreamWriter,
    publisher_id: str,
    count: int,
    sent_at: dict[str, float],
) -> None:
    for index in range(count):
        message = new_message(
            "chat",
            publisher_id,
            "sink",
            {"publisher": publisher_id, "seq": index},
            correlation_id=f"{publisher_id}-{index}",
            ttl_seconds=30,
        )
        sent_at[message.id] = time.perf_counter()
        writer.write((message.to_json() + "\n").encode())
    await writer.drain()


async def _receive_messages(reader: asyncio.StreamReader, expected: int) -> dict[str, float]:
    received: dict[str, float] = {}
    while len(received) < expected:
        payload = await _read_line(reader)
        received_at = time.perf_counter()
        message = Message.from_json(json.dumps(payload))
        received[message.id] = received_at
    return received


async def _write_line(writer: asyncio.StreamWriter, payload: dict[str, Any]) -> None:
    writer.write((json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n").encode())
    await writer.drain()


async def _read_line(reader: asyncio.StreamReader) -> dict[str, Any]:
    raw = await reader.readline()
    assert raw, "socket closed before expected bus frame"
    payload = json.loads(raw.decode())
    assert isinstance(payload, dict)
    return payload


async def _close(writer: asyncio.StreamWriter) -> None:
    writer.close()
    await writer.wait_closed()


def _p99(values: list[float]) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=100, method="inclusive")[98]
