import re
from typing import List, Optional, Callable, Dict, Any, Awaitable
from pydantic import BaseModel, Field

# --- Configuration ---
class ChunkingConfig(BaseModel):
    """
    Configuration for document chunking strategies.
    """
    strategy: str = Field(
        default="recursive", 
        description="Available strategies: 'recursive', 'fixed_size', 'semantic', 'markdown'"
    )
    chunk_size: int = Field(
        default=1000, 
        description="Maximum size of a chunk (in characters or tokens)"
    )
    chunk_overlap: int = Field(
        default=200, 
        description="Amount of overlap between chunks"
    )
    semantic_threshold: float = Field(
        default=0.75, 
        description="Cosine similarity threshold for boundary detection in semantic chunking"
    )

# --- Chunking Strategies ---

class RecursiveTextSplitter:
    """
    Splits text recursively by trying different separators (paragraphs, sentences, words).
    """
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        # Descending order of separator priority
        self.separators = ["\n\n", "\n", ". ", " ", ""]

    def split_text(self, text: str) -> List[str]:
        return self._split_recursive(text, self.separators)

    def _split_recursive(self, text: str, separators: List[str]) -> List[str]:
        if len(text) <= self.chunk_size:
            return [text]

        # Find the first separator that actually exists in the text
        separator = separators[0] if separators else ""
        for sep in separators:
            if sep == "":
                separator = sep
                break
            if sep in text:
                separator = sep
                break

        splits = text.split(separator) if separator else list(text)
        
        chunks = []
        current_chunk = ""

        for split in splits:
            merged = (current_chunk + separator + split) if current_chunk else split
                
            if len(merged) > self.chunk_size:
                if current_chunk:
                    chunks.append(current_chunk)
                    # Simplified overlap handling: starting next chunk with the current split
                    current_chunk = split
                else:
                    # The single split itself is larger than chunk_size, we must recurse deeper
                    if len(separators) > 1:
                        sub_chunks = self._split_recursive(split, separators[1:])
                        chunks.extend(sub_chunks)
                    else:
                        chunks.append(split)
            else:
                current_chunk = merged

        if current_chunk:
            chunks.append(current_chunk)
            
        return chunks


class FixedSizeChunker:
    """
    Splits text strictly by fixed size (characters or tokens) with overlap.
    """
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split_text(self, text: str) -> List[str]:
        chunks = []
        start = 0
        text_length = len(text)
        
        if text_length <= self.chunk_size:
            return [text]
            
        while start < text_length:
            end = min(start + self.chunk_size, text_length)
            chunks.append(text[start:end])
            
            if end == text_length:
                break
                
            # Move the start forward by chunk_size - overlap
            start = end - self.chunk_overlap
            
        return chunks


class SemanticChunker:
    """
    Splits text by detecting semantic topic boundaries using embeddings.
    """
    def __init__(
        self, 
        embedding_function: Callable[[str], Awaitable[List[float]]], 
        similarity_threshold: float = 0.75
    ):
        self.embedding_function = embedding_function
        self.similarity_threshold = similarity_threshold

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = sum(a * a for a in vec1) ** 0.5
        norm2 = sum(b * b for b in vec2) ** 0.5
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot_product / (norm1 * norm2)

    async def split_text(self, text: str) -> List[str]:
        # Basic sentence splitting to act as minimal semantic units
        sentences = re.split(r'(?<=[.!?]) +', text.strip())
        if not sentences:
            return []
            
        chunks = []
        current_chunk = sentences[0]
        # In a real system, you should batch embedding calls instead of looping iteratively
        current_embedding = await self.embedding_function(current_chunk)
        
        for sentence in sentences[1:]:
            sentence_embedding = await self.embedding_function(sentence)
            sim = self._cosine_similarity(current_embedding, sentence_embedding)
            
            if sim >= self.similarity_threshold:
                # Same topic, append to current chunk
                current_chunk += " " + sentence
            else:
                # Topic changed, save chunk and start new one
                chunks.append(current_chunk)
                current_chunk = sentence
                current_embedding = sentence_embedding
                
        if current_chunk:
            chunks.append(current_chunk)
            
        return chunks


class MarkdownChunker:
    """
    Splits text by markdown headers to preserve document structure.
    """
    def __init__(self, chunk_size: int = 1000):
        self.chunk_size = chunk_size

    def split_text(self, text: str) -> List[str]:
        # Regex to match markdown headers (e.g., # Header, ## Subheader)
        header_pattern = re.compile(r'(^#+\s+.*)', re.MULTILINE)
        parts = header_pattern.split(text)
        
        chunks = []
        current_chunk = ""
        
        for part in parts:
            if not part.strip():
                continue
                
            if header_pattern.match(part):
                # We hit a new header, meaning a new section starts
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = part
            else:
                # Append content to the current section
                current_chunk += "\n" + part
                
                # Note: if a markdown section is strictly longer than self.chunk_size, 
                # a production chunker would fall back to RecursiveTextSplitter here.
                
        if current_chunk:
            chunks.append(current_chunk.strip())
            
        return chunks
