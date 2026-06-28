from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from rag_pipeline import RAGPipeline, build_rag_router
from rag_pipeline.service import load_documents


def test_rag_pipeline_loads_documents_and_retrieves_relevant_context(tmp_path: Path) -> None:
    control_doc = tmp_path / "control.py"
    control_doc.write_text(
        "\n".join(
            [
                "def ready(state):",
                "    postgres_ok = run_postgres_probe(state)",
                "    redis_ok = state.redis_client.ping()",
                "    return postgres_ok and redis_ok",
            ]
        ),
        encoding="utf-8",
    )
    deploy_doc = tmp_path / "deploy.md"
    deploy_doc.write_text("The frontend listens on port 13000 during local deploy.", encoding="utf-8")

    pipeline = RAGPipeline.from_paths([tmp_path], chunk_size=240, chunk_overlap=20)
    result = pipeline.query("How does the ready health check validate postgres?", top_k=2)

    assert result.backend.startswith("local-hashing")
    assert result.document_count == 2
    assert result.chunk_count >= 2
    assert result.citations
    assert result.citations[0].source.endswith("control.py")
    assert "postgres" in result.answer.lower()


def test_loader_ignores_cache_and_binary_like_files(tmp_path: Path) -> None:
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "ignored.py").write_text("postgres redis", encoding="utf-8")
    (tmp_path / "notes.md").write_text("control-plane coupling health", encoding="utf-8")
    (tmp_path / "image.bin").write_bytes(b"\x00\x01")

    documents = load_documents([tmp_path])

    assert [Path(document.path).name for document in documents] == ["notes.md"]


def test_rag_router_returns_query_response(tmp_path: Path) -> None:
    (tmp_path / "main.py").write_text(
        "app.include_router(build_llm_gateway_router(config))\n"
        "app.include_router(build_rag_router(default_roots=[control_plane]))\n",
        encoding="utf-8",
    )
    app = FastAPI()
    app.include_router(build_rag_router(default_roots=[str(tmp_path)], prefix="/rag"))
    client = TestClient(app)

    health = client.get("/rag/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    response = client.post("/rag/query", json={"question": "Which router is included for RAG?", "top_k": 1})

    assert response.status_code == 200
    payload = response.json()
    assert payload["citations"]
    assert payload["document_count"] == 1
    assert "placeholder" not in payload["answer"].lower()
    assert payload["citations"][0]["source"].endswith("main.py")
