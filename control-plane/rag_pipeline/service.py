"""Document loading and local vector retrieval for control-plane RAG."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Mapping, Sequence


SUPPORTED_EXTENSIONS = {
    ".cfg",
    ".env.example",
    ".ini",
    ".json",
    ".md",
    ".py",
    ".sql",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}
IGNORED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}
TOKEN_RE = re.compile(r"[A-Za-z0-9_./:-]+")
STOPWORDS = {
    "a",
    "an",
    "and",
    "as",
    "does",
    "for",
    "how",
    "in",
    "is",
    "on",
    "or",
    "the",
    "to",
    "what",
    "which",
    "with",
}


@dataclass(frozen=True, slots=True)
class Document:
    """A source document loaded from the workspace."""

    path: str
    text: str


@dataclass(frozen=True, slots=True)
class RetrievalChunk:
    """A searchable document chunk with source coordinates."""

    id: str
    source: str
    text: str
    start_line: int
    end_line: int


@dataclass(frozen=True, slots=True)
class Citation:
    """A retrieved context citation returned to API callers."""

    source: str
    start_line: int
    end_line: int
    score: float
    snippet: str


@dataclass(frozen=True, slots=True)
class RAGQueryResult:
    """Answer and retrieval metadata for a RAG query."""

    question: str
    answer: str
    citations: tuple[Citation, ...]
    backend: str
    document_count: int
    chunk_count: int


class RAGPipeline:
    """Small RAG pipeline with optional framework detection and local retrieval.

    The control-plane deployment cannot assume provider credentials or heavyweight
    embedding dependencies. This implementation keeps the integration ready for
    LangChain/LlamaIndex while providing a deterministic local vector backend.
    """

    def __init__(
        self,
        documents: Sequence[Document],
        *,
        chunk_size: int = 1400,
        chunk_overlap: int = 180,
        backend: str | None = None,
    ) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be non-negative and smaller than chunk_size")
        self.documents = tuple(documents)
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.backend = backend or _detect_backend()
        self.chunks = tuple(self._chunk_documents(self.documents))
        self._vectors = tuple(_vectorize(chunk.text) for chunk in self.chunks)
        self._idf = _idf(self._vectors)

    @classmethod
    def from_paths(
        cls,
        paths: Sequence[str | Path],
        *,
        chunk_size: int = 1400,
        chunk_overlap: int = 180,
    ) -> "RAGPipeline":
        """Load documents recursively from files/directories and build an index."""

        documents = load_documents(paths)
        return cls(documents, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    def query(self, question: str, *, top_k: int = 4) -> RAGQueryResult:
        """Retrieve context and return an extractive answer with citations."""

        normalized_question = question.strip()
        if not normalized_question:
            raise ValueError("question must not be empty")
        if top_k <= 0:
            raise ValueError("top_k must be positive")

        query_vector = _vectorize(normalized_question)
        scored: list[tuple[float, RetrievalChunk]] = []
        for chunk, vector in zip(self.chunks, self._vectors, strict=True):
            score = _cosine(query_vector, vector, self._idf)
            keyword_overlap = _keyword_overlap(query_vector, vector)
            combined = score + (0.05 * keyword_overlap)
            if combined > 0:
                scored.append((combined, chunk))

        scored.sort(key=lambda item: item[0], reverse=True)
        selected = scored[:top_k]
        citations = tuple(
            Citation(
                source=chunk.source,
                start_line=chunk.start_line,
                end_line=chunk.end_line,
                score=round(score, 6),
                snippet=_snippet(chunk.text),
            )
            for score, chunk in selected
        )
        return RAGQueryResult(
            question=normalized_question,
            answer=_build_answer(normalized_question, citations),
            citations=citations,
            backend=self.backend,
            document_count=len(self.documents),
            chunk_count=len(self.chunks),
        )

    def _chunk_documents(self, documents: Sequence[Document]) -> Iterable[RetrievalChunk]:
        for document in documents:
            lines = document.text.splitlines()
            if not lines:
                continue
            current: list[str] = []
            start_line = 1
            current_size = 0
            chunk_number = 1
            for line_number, line in enumerate(lines, start=1):
                extra_size = len(line) + 1
                if current and current_size + extra_size > self.chunk_size:
                    text = "\n".join(current)
                    yield RetrievalChunk(
                        id=f"{document.path}:{chunk_number}",
                        source=document.path,
                        text=text,
                        start_line=start_line,
                        end_line=line_number - 1,
                    )
                    chunk_number += 1
                    overlap_lines = _overlap_lines(current, self.chunk_overlap)
                    current = overlap_lines + [line]
                    start_line = max(1, line_number - len(overlap_lines))
                    current_size = sum(len(item) + 1 for item in current)
                else:
                    current.append(line)
                    current_size += extra_size
            if current:
                yield RetrievalChunk(
                    id=f"{document.path}:{chunk_number}",
                    source=document.path,
                    text="\n".join(current),
                    start_line=start_line,
                    end_line=len(lines),
                )


def load_documents(paths: Sequence[str | Path]) -> tuple[Document, ...]:
    """Load supported text documents from files or directories."""

    documents: list[Document] = []
    for path in paths:
        root = Path(path).expanduser().resolve()
        if root.is_file() and _is_supported(root):
            document = _read_document(root)
            if document is not None:
                documents.append(document)
        elif root.is_dir():
            for candidate in sorted(root.rglob("*")):
                if _should_skip(candidate) or not candidate.is_file() or not _is_supported(candidate):
                    continue
                document = _read_document(candidate)
                if document is not None:
                    documents.append(document)
    return tuple(documents)


@lru_cache(maxsize=1)
def default_control_plane_roots() -> tuple[str, ...]:
    """Default knowledge roots for control-plane questions."""

    control_plane = Path(__file__).resolve().parents[1]
    repo_root = control_plane.parent
    roots = [
        control_plane / "app",
        control_plane / "core",
        control_plane / "coupling",
        control_plane / "executors",
        control_plane / "llm_gateway",
        control_plane / "messaging",
        control_plane / "orchestrator",
        control_plane / "registry",
        control_plane / "rag_pipeline",
        control_plane / "tasks_api",
        repo_root / "docs",
    ]
    return tuple(str(path) for path in roots if path.exists())


def _detect_backend() -> str:
    has_langchain = _can_import("langchain")
    has_llama_index = _can_import("llama_index")
    if has_langchain and has_llama_index:
        return "local-hashing+langchain+llamaindex-available"
    if has_langchain:
        return "local-hashing+langchain-available"
    if has_llama_index:
        return "local-hashing+llamaindex-available"
    return "local-hashing"


def _can_import(module: str) -> bool:
    try:
        __import__(module)
    except ImportError:
        return False
    return True


def _read_document(path: Path) -> Document | None:
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            text = path.read_text(encoding="latin-1")
        except UnicodeDecodeError:
            return None
    except OSError:
        return None
    if not text.strip():
        return None
    return Document(path=str(path), text=text)


def _should_skip(path: Path) -> bool:
    return any(part in IGNORED_DIRS or part.startswith(".") for part in path.parts)


def _is_supported(path: Path) -> bool:
    if path.name == ".env.example":
        return True
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for raw_token in TOKEN_RE.findall(text):
        for token in re.split(r"[_./:-]+", raw_token.lower()):
            if token and token not in STOPWORDS:
                tokens.append(token)
    return tokens


def _vectorize(text: str) -> Counter[str]:
    return Counter(_tokenize(text))


def _idf(vectors: Sequence[Mapping[str, int]]) -> dict[str, float]:
    doc_count = len(vectors)
    frequencies: Counter[str] = Counter()
    for vector in vectors:
        frequencies.update(vector.keys())
    return {
        token: math.log((1 + doc_count) / (1 + frequency)) + 1
        for token, frequency in frequencies.items()
    }


def _cosine(left: Mapping[str, int], right: Mapping[str, int], idf: Mapping[str, float]) -> float:
    if not left or not right:
        return 0.0
    common = set(left).intersection(right)
    numerator = sum(left[token] * right[token] * (idf.get(token, 1.0) ** 2) for token in common)
    left_norm = math.sqrt(sum((count * idf.get(token, 1.0)) ** 2 for token, count in left.items()))
    right_norm = math.sqrt(sum((count * idf.get(token, 1.0)) ** 2 for token, count in right.items()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


def _keyword_overlap(left: Mapping[str, int], right: Mapping[str, int]) -> float:
    if not left:
        return 0.0
    return len(set(left).intersection(right)) / len(set(left))


def _overlap_lines(lines: Sequence[str], max_chars: int) -> list[str]:
    if max_chars <= 0:
        return []
    selected: list[str] = []
    total = 0
    for line in reversed(lines):
        total += len(line) + 1
        if total > max_chars:
            break
        selected.insert(0, line)
    return selected


def _snippet(text: str, *, max_length: int = 420) -> str:
    collapsed = " ".join(line.strip() for line in text.splitlines() if line.strip())
    if len(collapsed) <= max_length:
        return collapsed
    return f"{collapsed[: max_length - 3].rstrip()}..."


def _build_answer(question: str, citations: Sequence[Citation]) -> str:
    if not citations:
        return (
            "Nao encontrei contexto relevante nos documentos indexados do control-plane "
            f"para responder: {question}"
        )
    primary = citations[0]
    source_name = Path(primary.source).name
    return (
        f"Com base no contexto mais relevante em {source_name}, "
        f"linhas {primary.start_line}-{primary.end_line}: {primary.snippet}"
    )
