"""FastAPI routes for the control-plane RAG pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from .service import RAGPipeline, default_control_plane_roots


class RAGQueryRequest(BaseModel):
    question: str = Field(..., min_length=1)
    paths: list[str] | None = None
    top_k: int = Field(default=4, ge=1, le=12)


class RAGCitationResponse(BaseModel):
    source: str
    start_line: int
    end_line: int
    score: float
    snippet: str


class RAGQueryResponse(BaseModel):
    question: str
    answer: str
    citations: list[RAGCitationResponse]
    backend: str
    document_count: int
    chunk_count: int


class RAGHealthResponse(BaseModel):
    status: str
    backend: str
    default_roots: list[str]


def build_rag_router(*, default_roots: list[str] | tuple[str, ...] | None = None, prefix: str = "/rag") -> APIRouter:
    """Build RAG query routes."""

    roots = tuple(default_roots or default_control_plane_roots())
    router = APIRouter(prefix=prefix, tags=["rag"])

    @router.get("/health", response_model=RAGHealthResponse)
    def health() -> RAGHealthResponse:
        return RAGHealthResponse(
            status="ok",
            backend=RAGPipeline([]).backend,
            default_roots=list(roots),
        )

    @router.post("/query", response_model=RAGQueryResponse)
    def query(request: RAGQueryRequest) -> RAGQueryResponse:
        query_roots = tuple(request.paths or roots)
        if not query_roots:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="no RAG document roots configured",
            )
        invalid = [path for path in query_roots if not Path(path).expanduser().exists()]
        if invalid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"invalid_paths": invalid},
            )
        try:
            result = RAGPipeline.from_paths(query_roots).query(request.question, top_k=request.top_k)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        return RAGQueryResponse(
            question=result.question,
            answer=result.answer,
            citations=[
                RAGCitationResponse(
                    source=citation.source,
                    start_line=citation.start_line,
                    end_line=citation.end_line,
                    score=citation.score,
                    snippet=citation.snippet,
                )
                for citation in result.citations
            ],
            backend=result.backend,
            document_count=result.document_count,
            chunk_count=result.chunk_count,
        )

    @router.get("/topology", response_model=dict[str, Any])
    def topology() -> dict[str, Any]:
        return {
            "default_roots": list(roots),
            "supported_routes": [f"{prefix}/health", f"{prefix}/query"],
        }

    return router
