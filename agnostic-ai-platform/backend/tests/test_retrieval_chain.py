from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app.auth import create_access_token
import app.retrieval_chain as retrieval_chain
from app.retrieval_chain import (
    LOCAL_EMBEDDING_MODEL,
    RetrievalDocument,
    assemble_context_window,
    build_rag_prompt,
    embed_documents,
    generate_query_embedding,
    vector_similarity_search,
)


def auth_headers() -> dict[str, str]:
    token = create_access_token(user_id="user-1", role="admin", tenant_id="tenant-1")
    return {"Authorization": f"Bearer {token}", "x-workspace": "rag-workspace", "x-user": "rag-user"}


async def fake_acompletion(*, model: str, messages: list[dict[str, str]], **kwargs: Any) -> dict[str, Any]:
    assert model == "gpt-4o-mini"
    assert "Context:" in messages[-1]["content"]
    assert "Postgres stores relational data" in messages[-1]["content"]
    return {
        "id": "chatcmpl-rag",
        "model": model,
        "choices": [{"message": {"role": "assistant", "content": "Postgres stores relational data."}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }


def test_query_embedding_and_similarity_search_rank_relevant_chunk() -> None:
    documents = [
        RetrievalDocument(text="Postgres stores relational data", metadata={"source": "db.md"}),
        RetrievalDocument(text="Redis is an in-memory cache", metadata={"source": "cache.md"}),
    ]

    import asyncio

    embedded = asyncio.run(embed_documents(documents, embedding_model=LOCAL_EMBEDDING_MODEL))
    query_embedding = asyncio.run(generate_query_embedding("Where is relational data stored?", model=LOCAL_EMBEDDING_MODEL))
    results = vector_similarity_search(query_embedding, embedded, top_k=1)

    assert results[0].metadata["source"] == "db.md"
    assert results[0].score > 0


def test_context_window_and_prompt_inject_retrieved_context() -> None:
    chunk = retrieval_chain.RetrievedChunk(
        id="chunk-1",
        text="Postgres stores relational data",
        score=0.9,
        metadata={"source": "db.md", "page": 2},
    )

    context = assemble_context_window([chunk], max_context_chars=500)
    prompt = build_rag_prompt(query="What stores relational data?", context=context)

    assert "[source 1: db.md, page 2; score=0.900]" in context
    assert "Postgres stores relational data" in prompt[-1]["content"]
    assert "What stores relational data?" in prompt[-1]["content"]


def test_rag_query_endpoint_uses_inline_documents_and_llm_completion(monkeypatch) -> None:
    from app.main import create_app

    monkeypatch.setattr(retrieval_chain.litellm, "acompletion", fake_acompletion)
    client = TestClient(create_app())

    response = client.post(
        "/v1/rag/query",
        headers=auth_headers(),
        json={
            "query": "Where is relational data stored?",
            "embedding_model": LOCAL_EMBEDDING_MODEL,
            "documents": [
                {"text": "Postgres stores relational data", "metadata": {"source": "db.md"}},
                {"text": "Redis is an in-memory cache", "metadata": {"source": "cache.md"}},
            ],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Postgres stores relational data."
    assert body["retrieved_chunks"][0]["metadata"]["source"] == "db.md"
    assert body["prompt_tokens"] == 10
    assert body["completion_tokens"] == 5
    assert body["total_tokens"] == 15


def test_rag_query_endpoint_returns_404_without_context() -> None:
    from app.main import create_app

    retrieval_chain.GLOBAL_VECTOR_INDEX.clear()
    client = TestClient(create_app())

    response = client.post(
        "/v1/rag/query",
        headers=auth_headers(),
        json={"query": "What is indexed?", "embedding_model": LOCAL_EMBEDDING_MODEL},
    )

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "no_context"
