"""RAG pipeline for control-plane knowledge queries."""

from .router import build_rag_router
from .service import (
    Citation,
    Document,
    RAGPipeline,
    RAGQueryResult,
    RetrievalChunk,
)

__all__ = [
    "Citation",
    "Document",
    "RAGPipeline",
    "RAGQueryResult",
    "RetrievalChunk",
    "build_rag_router",
]
