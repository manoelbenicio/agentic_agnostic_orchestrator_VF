import logging
from typing import List, Dict, Any, Optional

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, Mapped, mapped_column, sessionmaker
from sqlalchemy import select, text, String, JSON, Index
from pgvector.sqlalchemy import Vector

logger = logging.getLogger(__name__)

Base = declarative_base()

class DocumentChunk(Base):
    """
    SQLAlchemy model representing a document chunk with an embedding vector.
    """
    __tablename__ = 'document_chunks'

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    content: Mapped[str] = mapped_column(String)
    
    # 'metadata' is a reserved property in SQLAlchemy Base, so we use 'metadata_' 
    # but map it to the 'metadata' column in the database.
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default={})
    
    # Define vector column with dimensions matching the embedding model 
    # (e.g., 1536 for text-embedding-ada-002, or 768 for open source models)
    embedding: Mapped[list] = mapped_column(Vector(1536))

# --- Index Management ---
# Create an HNSW (Hierarchical Navigable Small World) index for fast approximate nearest neighbor search.
# Using 'vector_cosine_ops' optimizes the index specifically for cosine similarity calculations.
Index(
    'ix_document_chunks_embedding_hnsw', 
    DocumentChunk.embedding, 
    postgresql_using='hnsw', 
    postgresql_with={'m': 16, 'ef_construction': 64}, 
    postgresql_ops={'embedding': 'vector_cosine_ops'}
)

class PGVectorManager:
    """
    Manager for pgvector connections, embedding storage, batch operations, and similarity search.
    """
    def __init__(self, database_url: str):
        # Initialize async SQLAlchemy engine
        self.engine = create_async_engine(database_url, echo=False)
        self.async_session = sessionmaker(
            self.engine, class_=AsyncSession, expire_on_commit=False
        )

    async def initialize_database(self):
        """
        Creates the pgvector extension (if not exists), tables, and HNSW indexes.
        """
        async with self.engine.begin() as conn:
            # Must install the pgvector extension before creating vector columns
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            # Synchronously create tables and apply indices
            await conn.run_sync(Base.metadata.create_all)
            logger.info("pgvector database, tables, and HNSW indices initialized successfully.")

    async def batch_upsert(self, chunks: List[Dict[str, Any]]):
        """
        Batch upsert document chunks into the vector store.
        
        Args:
            chunks: A list of dicts containing 'id', 'tenant_id', 'content', 'metadata', and 'embedding'.
        """
        async with self.async_session() as session:
            async with session.begin():
                for chunk_data in chunks:
                    # Using merge() performs an upsert by primary key (id)
                    chunk = DocumentChunk(
                        id=chunk_data['id'],
                        tenant_id=chunk_data['tenant_id'],
                        content=chunk_data['content'],
                        metadata_=chunk_data.get('metadata', {}),
                        embedding=chunk_data['embedding']
                    )
                    await session.merge(chunk)
            logger.info(f"Successfully upserted {len(chunks)} document chunks.")

    async def similarity_search(
        self, 
        tenant_id: str, 
        query_embedding: List[float], 
        top_k: int = 5, 
        score_threshold: float = 0.7
    ) -> List[Dict[str, Any]]:
        """
        Retrieve the most relevant chunks using cosine similarity.
        
        Returns chunks ordered by similarity score, filtered by a minimum score threshold.
        """
        async with self.async_session() as session:
            # In pgvector, `<=>` computes cosine distance.
            # Cosine Similarity is equal to 1 - Cosine Distance.
            similarity = (1 - DocumentChunk.embedding.cosine_distance(query_embedding)).label("similarity")
            
            # Construct the query
            stmt = (
                select(DocumentChunk, similarity)
                .where(DocumentChunk.tenant_id == tenant_id)
                # Filter out chunks that do not meet the minimum similarity threshold
                .where(similarity >= score_threshold)
                # Order by closest vectors (cosine distance ascending)
                .order_by(DocumentChunk.embedding.cosine_distance(query_embedding))
                .limit(top_k)
            )
            
            result = await session.execute(stmt)
            rows = result.all()
            
            # Format results
            results = []
            for chunk, sim_score in rows:
                results.append({
                    "id": chunk.id,
                    "content": chunk.content,
                    "metadata": chunk.metadata_,
                    "score": float(sim_score)
                })
                
            return results

    async def close(self):
        """Properly close the database connection pool."""
        await self.engine.dispose()
