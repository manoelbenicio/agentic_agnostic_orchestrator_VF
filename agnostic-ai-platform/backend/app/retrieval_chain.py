from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import math
import os
import re
from typing import Any
from uuid import uuid4

import litellm
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.metrics import record_llm_token_usage
from app.tracing import llm_request_span


DEFAULT_EMBEDDING_MODEL = os.getenv("AOP_RAG_EMBEDDING_MODEL", "text-embedding-3-small")
DEFAULT_LLM_MODEL = os.getenv("AOP_RAG_LLM_MODEL", "gpt-4o-mini")
DEFAULT_CONTEXT_CHARS = 6000
LOCAL_EMBEDDING_MODEL = "local-hash"
HASH_EMBEDDING_DIMENSIONS = 256

SYSTEM_PROMPT = """You answer using only the retrieved context.
If the context does not contain enough information, say that the available context is insufficient.
Keep the answer concise and cite sources using the provided source labels."""

USER_PROMPT_TEMPLATE = """Context:
{context}

Question:
{query}"""

router = APIRouter(prefix="/v1/rag", tags=["RAG"])


class RetrievalDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class RetrievedChunk(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    text: str
    score: float = Field(ge=-1.0, le=1.0)
    metadata: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class RAGQueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1)
    model: str = Field(default=DEFAULT_LLM_MODEL, min_length=1)
    provider: str | None = Field(default=None)
    embedding_model: str = Field(default=DEFAULT_EMBEDDING_MODEL, min_length=1)
    documents: list[RetrievalDocument] = Field(default_factory=list)
    top_k: int = Field(default=4, ge=1, le=20)
    min_score: float = Field(default=0.0, ge=-1.0, le=1.0)
    max_context_chars: int = Field(default=DEFAULT_CONTEXT_CHARS, ge=500, le=30000)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, gt=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("query")
    @classmethod
    def query_not_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("query must not be blank")
        return stripped


class RAGQueryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str
    model: str
    provider: str
    prompt: str
    context: str
    retrieved_chunks: list[RetrievedChunk]
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    response_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RAGIndexRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    documents: list[RetrievalDocument] = Field(min_length=1)
    embedding_model: str = Field(default=DEFAULT_EMBEDDING_MODEL, min_length=1)


class RAGIndexResponse(BaseModel):
    indexed_chunks: int
    embedding_model: str


@dataclass(frozen=True, slots=True)
class EmbeddedChunk:
    id: str
    text: str
    metadata: dict[str, str | int | float | bool | None]
    embedding: list[float]


class InMemoryVectorIndex:
    def __init__(self) -> None:
        self._chunks: list[EmbeddedChunk] = []

    def clear(self) -> None:
        self._chunks.clear()

    def add(self, chunks: list[EmbeddedChunk]) -> None:
        self._chunks.extend(chunks)

    def search(self, embedding: list[float], *, top_k: int, min_score: float = 0.0) -> list[RetrievedChunk]:
        scored = [
            RetrievedChunk(id=chunk.id, text=chunk.text, score=_cosine_similarity(embedding, chunk.embedding), metadata=chunk.metadata)
            for chunk in self._chunks
        ]
        scored.sort(key=lambda item: item.score, reverse=True)
        return [item for item in scored if item.score >= min_score][:top_k]

    def __len__(self) -> int:
        return len(self._chunks)


GLOBAL_VECTOR_INDEX = InMemoryVectorIndex()


async def generate_embeddings(texts: list[str], *, model: str = DEFAULT_EMBEDDING_MODEL) -> list[list[float]]:
    if not texts:
        return []
    if _use_local_embeddings(model):
        return [_hash_embedding(text) for text in texts]

    response = await litellm.aembedding(model=model, input=texts)
    data = _get_value(response, "data") or []
    embeddings = [_get_value(item, "embedding") for item in data]
    if len(embeddings) != len(texts) or any(not isinstance(item, list) for item in embeddings):
        raise RuntimeError("embedding provider returned an invalid embedding payload")
    return [[float(value) for value in embedding] for embedding in embeddings]


async def generate_query_embedding(query: str, *, model: str = DEFAULT_EMBEDDING_MODEL) -> list[float]:
    embeddings = await generate_embeddings([query], model=model)
    if not embeddings:
        raise RuntimeError("embedding provider returned no query embedding")
    return embeddings[0]


async def embed_documents(
    documents: list[RetrievalDocument],
    *,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
) -> list[EmbeddedChunk]:
    embeddings = await generate_embeddings([document.text for document in documents], model=embedding_model)
    return [
        EmbeddedChunk(id=str(uuid4()), text=document.text, metadata=document.metadata, embedding=embedding)
        for document, embedding in zip(documents, embeddings, strict=True)
    ]


def vector_similarity_search(
    query_embedding: list[float],
    chunks: list[EmbeddedChunk],
    *,
    top_k: int,
    min_score: float = 0.0,
) -> list[RetrievedChunk]:
    index = InMemoryVectorIndex()
    index.add(chunks)
    return index.search(query_embedding, top_k=top_k, min_score=min_score)


def assemble_context_window(chunks: list[RetrievedChunk], *, max_context_chars: int = DEFAULT_CONTEXT_CHARS) -> str:
    blocks: list[str] = []
    remaining = max_context_chars
    for index, chunk in enumerate(chunks, start=1):
        source = chunk.metadata.get("source") or chunk.metadata.get("filename") or chunk.id
        page = chunk.metadata.get("page")
        label = f"source {index}: {source}" + (f", page {page}" if page is not None else "")
        block = f"[{label}; score={chunk.score:.3f}]\n{chunk.text.strip()}"
        if len(block) > remaining:
            block = block[: max(remaining - 3, 0)].rstrip() + "..."
        if not block.strip():
            break
        blocks.append(block)
        remaining -= len(block) + 2
        if remaining <= 0:
            break
    return "\n\n".join(blocks)


def build_rag_prompt(*, query: str, context: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_PROMPT_TEMPLATE.format(context=context or "No relevant context retrieved.", query=query)},
    ]


class RetrievalChain:
    def __init__(self, *, vector_index: InMemoryVectorIndex | None = None) -> None:
        self.vector_index = vector_index or GLOBAL_VECTOR_INDEX

    async def query(self, request: RAGQueryRequest, *, workspace: str = "default", user: str = "anonymous") -> RAGQueryResponse:
        chunks = await self._retrieved_chunks(request)
        if not chunks:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "no_context", "message": "No indexed or inline documents matched the query."},
            )

        context = assemble_context_window(chunks, max_context_chars=request.max_context_chars)
        messages = build_rag_prompt(query=request.query, context=context)
        resolved_model = resolve_litellm_model(request.model, request.provider)
        provider = infer_provider_from_model(resolved_model, request.provider)

        litellm_kwargs: dict[str, Any] = {
            "messages": messages,
            "temperature": request.temperature,
            "metadata": {
                **request.metadata,
                "workspace": workspace,
                "user": user,
                "rag_top_k": request.top_k,
                "rag_context_chars": len(context),
            },
        }
        if request.max_tokens is not None:
            litellm_kwargs["max_tokens"] = request.max_tokens

        with llm_request_span(model=resolved_model, provider=provider, workspace=workspace, user=user, metadata=litellm_kwargs["metadata"]):
            response = await litellm.acompletion(model=resolved_model, **litellm_kwargs)

        answer, finish_reason = _completion_text(response)
        prompt_tokens, completion_tokens, total_tokens = _usage_tokens(response)
        record_llm_token_usage(
            model=resolved_model,
            provider=provider,
            workspace=workspace,
            user=user,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )

        return RAGQueryResponse(
            answer=answer,
            model=str(_get_value(response, "model") or resolved_model),
            provider=provider,
            prompt=messages[-1]["content"],
            context=context,
            retrieved_chunks=chunks,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            response_id=_get_value(response, "id"),
            metadata={"finish_reason": finish_reason, "embedding_model": request.embedding_model},
        )

    async def _retrieved_chunks(self, request: RAGQueryRequest) -> list[RetrievedChunk]:
        query_embedding = await generate_query_embedding(request.query, model=request.embedding_model)
        if request.documents:
            embedded = await embed_documents(request.documents, embedding_model=request.embedding_model)
            return vector_similarity_search(
                query_embedding,
                embedded,
                top_k=request.top_k,
                min_score=request.min_score,
            )
        return self.vector_index.search(query_embedding, top_k=request.top_k, min_score=request.min_score)


_chain = RetrievalChain()


@router.post("/index", response_model=RAGIndexResponse, status_code=status.HTTP_200_OK)
async def index_documents(request: RAGIndexRequest) -> RAGIndexResponse:
    chunks = await embed_documents(request.documents, embedding_model=request.embedding_model)
    GLOBAL_VECTOR_INDEX.add(chunks)
    return RAGIndexResponse(indexed_chunks=len(chunks), embedding_model=request.embedding_model)


@router.post("/query", response_model=RAGQueryResponse, status_code=status.HTTP_200_OK)
async def query_rag(request: RAGQueryRequest, fastapi_request: Request) -> RAGQueryResponse:
    workspace = fastapi_request.headers.get("x-workspace", "default") or "default"
    user = fastapi_request.headers.get("x-user", "anonymous") or "anonymous"
    try:
        return await _chain.query(request, workspace=workspace, user=user)
    except litellm.AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": "provider_auth_error", "message": str(exc)}) from exc
    except litellm.BadRequestError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": "provider_bad_request", "message": str(exc)}) from exc
    except litellm.ContextWindowExceededError as exc:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail={"code": "context_window_exceeded", "message": str(exc)}) from exc
    except litellm.APIError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail={"code": "provider_error", "message": str(exc)}) from exc


def resolve_litellm_model(model: str, provider: str | None) -> str:
    if "/" in model or not provider:
        return model
    normalized = provider.strip().lower()
    if normalized in {"google", "gemini"}:
        return f"gemini/{model}"
    if normalized in {"anthropic", "claude"}:
        return f"anthropic/{model}"
    return model


def infer_provider_from_model(model: str, provider: str | None = None) -> str:
    if provider:
        normalized = provider.strip().lower()
        return "google" if normalized == "gemini" else normalized
    if "/" in model:
        prefix = model.split("/", 1)[0].lower()
        return "google" if prefix == "gemini" else prefix
    if model.startswith("claude-"):
        return "anthropic"
    if model.startswith("gemini-"):
        return "google"
    return "openai"


def _completion_text(response: Any) -> tuple[str, str]:
    choices = _get_value(response, "choices") or []
    if not choices:
        return "", "unknown"
    choice = choices[0]
    message = _get_value(choice, "message") or {}
    content = _get_value(message, "content")
    if content is None:
        content = _get_value(choice, "text") or ""
    return str(content), str(_get_value(choice, "finish_reason") or "stop")


def _usage_tokens(response: Any) -> tuple[int, int, int]:
    usage = _get_value(response, "usage") or {}
    prompt_tokens = _int_value(_get_value(usage, "prompt_tokens", "input_tokens"))
    completion_tokens = _int_value(_get_value(usage, "completion_tokens", "output_tokens"))
    total_tokens = _int_value(_get_value(usage, "total_tokens")) or prompt_tokens + completion_tokens
    return prompt_tokens, completion_tokens, total_tokens


def _use_local_embeddings(model: str) -> bool:
    return model == LOCAL_EMBEDDING_MODEL or os.getenv("AOP_RAG_LOCAL_EMBEDDINGS", "").lower() in {"1", "true", "yes"}


def _hash_embedding(text: str) -> list[float]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    counts = Counter(tokens)
    vector = [0.0] * HASH_EMBEDDING_DIMENSIONS
    for token, count in counts.items():
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % HASH_EMBEDDING_DIMENSIONS
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign * float(count)
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    size = min(len(left), len(right))
    dot = sum(left[index] * right[index] for index in range(size))
    left_norm = math.sqrt(sum(value * value for value in left[:size]))
    right_norm = math.sqrt(sum(value * value for value in right[:size]))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def _get_value(source: Any, *keys: str) -> Any:
    for key in keys:
        if isinstance(source, dict) and key in source:
            return source[key]
        if hasattr(source, key):
            return getattr(source, key)
    if hasattr(source, "model_dump"):
        dumped = source.model_dump()
        if isinstance(dumped, dict):
            return _get_value(dumped, *keys)
    return None


def _int_value(value: Any) -> int:
    try:
        return max(int(value or 0), 0)
    except (TypeError, ValueError):
        return 0
