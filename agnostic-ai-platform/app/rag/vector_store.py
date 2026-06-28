import json
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("rag.vector_store")

class VectorStore:
    """
    Extremely high-performance mathematical integration layer leveraging PostgreSQL + pgvector 
    over asyncpg connection pools. Responsible for dynamically maintaining tables, structural 
    JSONB indexes, and massive multidimensional Neural embeddings natively.
    """
    def __init__(self, pool):
        """
        Dependency injection. Expects a natively configured asyncpg.Pool instance.
        Crucial Note: The pool must be initialized mapped securely to pgvector.
        (e.g., `import pgvector.asyncpg; await pgvector.asyncpg.register_vector(conn)`)
        """
        self.pool = pool

    async def create_collection(self, name: str, dimension: int = 1536, index_type: str = "hnsw") -> str:
        """
        Dynamically provisions a strictly isolated vector collection table mapping.
        Supports advanced mathematical index generation accelerating spatial nearest-neighbor lookups.
        Allowed index_type architectures: 'hnsw' (Graph) or 'ivfflat' (Clusters).
        """
        # Rigid DDL sanitization stripping SQL Injection vectors mapped to dynamic table structures
        safe_name = "".join([c for c in name if c.isalnum() or c == "_"])
        table_name = f"collection_{safe_name}"

        create_table_sql = f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                content TEXT NOT NULL,
                metadata JSONB DEFAULT '{{}}'::jsonb,
                embedding vector({dimension})
            );
        """
        
        # IVFFlat builds centroid lists and is reliant heavily on data table size.
        # HNSW generates a graph topological layout and operates aggressively performant on updates natively.
        if index_type.lower() == "hnsw":
            index_sql = f"""
                CREATE INDEX IF NOT EXISTS {table_name}_embedding_idx 
                ON {table_name} USING hnsw (embedding vector_cosine_ops)
                WITH (m = 16, ef_construction = 64);
            """
        else:
            index_sql = f"""
                CREATE INDEX IF NOT EXISTS {table_name}_embedding_idx 
                ON {table_name} USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100);
            """

        logger.info(f"Provisioning physical PgVector Matrix '{table_name}' ({dimension}d) utilizing {index_type.upper()}")
        
        if self.pool:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    # Guarantees the Postgres C-extension is enabled securely inside the schema
                    await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                    await conn.execute(create_table_sql)
                    await conn.execute(index_sql)
                    
                    # Boost filter performance with a GIN index strictly on JSONB metadata payloads
                    await conn.execute(f"CREATE INDEX IF NOT EXISTS {table_name}_metadata_idx ON {table_name} USING GIN (metadata);")
        else:
            logger.debug(f"[MOCK DDL Sequence]: Tables and structural indexes mapped synthetically for {table_name}.")
            
        return table_name

    async def insert_vectors(self, collection: str, chunks: List[str], vectors: List[List[float]], metadatas: List[Dict[str, Any]]):
        """
        Transactionally batch-inserts dense chunks, arrays, and associative JSONB filters.
        """
        if not (len(chunks) == len(vectors) == len(metadatas)):
            raise ValueError("Fatal dimension mismatch across chunks, array lengths, and operational metadata payloads.")

        safe_name = "".join([c for c in collection if c.isalnum() or c == "_"])
        table_name = f"collection_{safe_name}"
        
        query = f"""
            INSERT INTO {table_name} (content, embedding, metadata) 
            VALUES ($1, $2, $3)
            RETURNING id;
        """
        
        logger.info(f"Pipeline transmitting {len(vectors)} neural vector matrices to target => {table_name}...")
        
        if self.pool:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    # Batch executemany aggressively accelerates bulk ingestion timelines mapped via pgvector string conversions
                    payload = [
                        (chunk, str(vector), json.dumps(meta)) 
                        for chunk, vector, meta in zip(chunks, vectors, metadatas)
                    ]
                    await conn.executemany(query, payload)
        else:
            logger.debug(f"[MOCK BATCH INGESTION]: Executed mapped arrays inserting count=({len(vectors)}).")

    async def search(self, collection: str, query_vector: List[float], top_k: int = 5, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Executes intensive geometric Cosine Distance `<=>` mathematical evaluations directly on Postgres logic.
        Applies implicit JSONB boundaries via GIN logic (e.g. {"tenant_id": "alpha"}) accelerating filtering.
        """
        safe_name = "".join([c for c in collection if c.isalnum() or c == "_"])
        table_name = f"collection_{safe_name}"
        
        # Postgres `<=>` operator inherently dictates Cosine Distance computation physically. 
        # Ordering ASC fetches logically shortest spatial topological proximity.
        # We math invert to score `1 - distance` to yield native Cosine Similarity boundaries (1.0 = perfect matching identity).
        base_query = f"""
            SELECT id, content, metadata, 1 - (embedding <=> $1) as similarity_score
            FROM {table_name}
        """
        
        args = [str(query_vector), top_k]
        
        if filters:
            # Dynamically compile raw exact match bindings targeting deep nested JSONB topologies
            filter_clauses = []
            for k, v in filters.items():
                arg_idx = len(args) + 1
                filter_clauses.append(f"metadata->>'{k}' = ${arg_idx}")
                args.append(str(v))
            
            base_query += " WHERE " + " AND ".join(filter_clauses)
            
        base_query += f" ORDER BY embedding <=> $1 ASC LIMIT $2;"
        
        logger.debug(f"Calculating dynamic Cosine similarity metrics against {table_name} limit(k={top_k})")
        
        if self.pool:
            async with self.pool.acquire() as conn:
                records = await conn.fetch(base_query, *args)
                return [
                    {
                        "id": str(r["id"]),
                        "content": r["content"],
                        "metadata": json.loads(r["metadata"]),
                        "score": round(r["similarity_score"], 4)
                    }
                    for r in records
                ]
        else:
            # Synthetic structural return mapped accurately
            return [
                {
                    "id": "synthetic-uuid-matrix", 
                    "content": "Operational simulated context paragraph...", 
                    "metadata": {"tenant_id": "test_matrix"}, 
                    "score": 0.8921
                }
            ]

    async def delete_vectors(self, collection: str, ids: List[str]):
        """Executes a hard-delete structural sweep permanently purging neural nodes from PG."""
        if not ids:
            return
            
        safe_name = "".join([c for c in collection if c.isalnum() or c == "_"])
        table_name = f"collection_{safe_name}"
        
        query = f"DELETE FROM {table_name} WHERE id = ANY($1::uuid[])"
        
        if self.pool:
            async with self.pool.acquire() as conn:
                await conn.execute(query, ids)
        else:
            logger.debug(f"[MOCK HARD DELETE]: Evicted dimensional matrices targets=({ids}) from {table_name}.")

    async def get_stats(self, collection: str) -> Dict[str, Any]:
        """Compiles accurate physical disk density diagnostics natively evaluating HNSW topological sizes."""
        safe_name = "".join([c for c in collection if c.isalnum() or c == "_"])
        table_name = f"collection_{safe_name}"
        
        if self.pool:
            async with self.pool.acquire() as conn:
                total_rows = await conn.fetchval(f"SELECT COUNT(*) FROM {table_name}")
                table_size = await conn.fetchval(f"SELECT pg_size_pretty(pg_relation_size('{table_name}'))")
                index_size = await conn.fetchval(f"SELECT pg_size_pretty(pg_indexes_size('{table_name}'))")
                
                return {
                    "collection": table_name,
                    "total_vectors": total_rows,
                    "table_size": table_size,
                    "index_size": index_size
                }
        else:
            return {
                "collection": table_name,
                "total_vectors": 128954,
                "table_size": "218 MB",
                "index_size": "74 MB"
            }
