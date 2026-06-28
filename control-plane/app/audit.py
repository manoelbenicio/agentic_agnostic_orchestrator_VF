import psycopg

def init_schema(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS audit_events (
                id BIGSERIAL PRIMARY KEY,
                timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                user_id TEXT NOT NULL,
                action TEXT NOT NULL,
                resource TEXT NOT NULL,
                trace_id TEXT NOT NULL
            );
        """)
        # Trigger to enforce immutable append-only log
        cur.execute("""
            CREATE OR REPLACE FUNCTION prevent_audit_modifications()
            RETURNS TRIGGER AS $$
            BEGIN
                RAISE EXCEPTION 'Audit log is append-only and immutable';
            END;
            $$ LANGUAGE plpgsql;
        """)
        cur.execute("""
            DROP TRIGGER IF EXISTS enforce_append_only ON audit_events;
            CREATE TRIGGER enforce_append_only
            BEFORE UPDATE OR DELETE ON audit_events
            FOR EACH ROW EXECUTE FUNCTION prevent_audit_modifications();
        """)
    conn.commit()

class AuditRepository:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def append(self, user_id: str, action: str, resource: str, trace_id: str) -> None:
        with self._conn.cursor() as cur:
            cur.execute("""
                INSERT INTO audit_events (user_id, action, resource, trace_id)
                VALUES (%s, %s, %s, %s)
            """, (user_id, action, resource, trace_id))
        self._conn.commit()
