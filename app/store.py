import json
import math

import psycopg
from psycopg.rows import dict_row

from app.config import DATABASE_URL, DIMENSIONS, EMBED_MODEL

SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS sources (
    id text PRIMARY KEY, candidate_id text, path text NOT NULL,
    name text NOT NULL, sha256 text NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
    id text PRIMARY KEY, source_id text NOT NULL REFERENCES sources(id),
    candidate_id text, section text NOT NULL, locator text NOT NULL,
    text text NOT NULL, embedding vector(1536) NOT NULL
);
CREATE TABLE IF NOT EXISTS index_metadata (
    key text PRIMARY KEY, value text NOT NULL
);
"""


def vector_literal(values):
    if len(values) != DIMENSIONS or not all(math.isfinite(v) for v in values):
        raise ValueError("Invalid embedding shape or values.")
    return "[" + ",".join(str(float(v)) for v in values) + "]"


class Store:
    def __init__(self, url=DATABASE_URL):
        self.url = url

    def connect(self):
        return psycopg.connect(self.url, row_factory=dict_row, connect_timeout=5)

    def replace(self, sources, chunks, vectors):
        if len(chunks) != len(vectors):
            raise ValueError("Embedding count mismatch.")
        values = [vector_literal(v) for v in vectors]
        # One transaction: a failed replacement keeps the previous usable index.
        with self.connect() as conn:
            conn.execute(SCHEMA)
            conn.execute("DELETE FROM chunks")
            conn.execute("DELETE FROM sources")
            with conn.cursor() as cursor:
                cursor.executemany(
                    "INSERT INTO sources VALUES (%s,%s,%s,%s,%s)",
                    [(s["id"], s["candidate_id"], s["path"], s["name"], s["sha256"])
                     for s in sources],
                )
                cursor.executemany(
                    "INSERT INTO chunks VALUES (%s,%s,%s,%s,%s,%s,%s::vector)",
                    [(c["id"], c["source_id"], c["candidate_id"], c["section"],
                      c["locator"], c["text"], v) for c, v in zip(chunks, values)],
                )
            conn.execute(
                "INSERT INTO index_metadata VALUES ('embed_model',%s) "
                "ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value", (EMBED_MODEL,)
            )

    def ready(self):
        with self.connect() as conn:
            row = conn.execute(
                "SELECT value FROM index_metadata WHERE key='embed_model'"
            ).fetchone()
            if not row or row["value"] != EMBED_MODEL:
                raise ValueError("Re-ingest using the configured embedding model.")
            count = conn.execute("SELECT count(*) AS n FROM chunks").fetchone()["n"]
            if not count:
                raise ValueError("Index is empty.")
            return count

    def candidates(self):
        with self.connect() as conn:
            return [r["candidate_id"] for r in conn.execute(
                "SELECT candidate_id FROM sources WHERE candidate_id IS NOT NULL "
                "ORDER BY candidate_id"
            )]

    def aliases(self):
        with self.connect() as conn:
            return {r["name"]: r["candidate_id"] for r in conn.execute(
                "SELECT name,candidate_id FROM sources WHERE candidate_id IS NOT NULL"
            ) if r["name"]}

    def criteria(self):
        with self.connect() as conn:
            return list(conn.execute(
                "SELECT id,section,text,locator FROM chunks WHERE source_id='JD' ORDER BY id"
            ))

    def all_evidence(self):
        with self.connect() as conn:
            return list(conn.execute(
                "SELECT id,source_id,candidate_id,section,locator,text FROM chunks "
                "WHERE candidate_id IS NOT NULL ORDER BY id"
            ))

    def search(self, vector, candidate_id=None, k=4):
        if not 1 <= k <= 20:
            raise ValueError("Invalid retrieval limit.")
        with self.connect() as conn:
            return list(conn.execute(
                "SELECT id,source_id,candidate_id,section,locator,text,"
                "1-(embedding <=> %s::vector) AS similarity FROM chunks "
                "WHERE candidate_id IS NOT NULL "
                "AND (%s::text IS NULL OR candidate_id=%s) "
                "ORDER BY embedding <=> %s::vector,id LIMIT %s",
                (vector_literal(vector), candidate_id, candidate_id,
                 vector_literal(vector), k),
            ))

    def fingerprint(self):
        with self.connect() as conn:
            rows = list(conn.execute("SELECT id,sha256 FROM sources ORDER BY id"))
        import hashlib
        return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()