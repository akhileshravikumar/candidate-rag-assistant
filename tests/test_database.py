import os
from urllib.parse import urlparse

import pytest

from app.config import DIMENSIONS
from app.store import Store

pytestmark = pytest.mark.integration


def test_real_pgvector_index_search_replace_and_rollback():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL for real pgvector integration.")
    if urlparse(url).path != "/rag_test":
        pytest.fail("Integration test must use the dedicated rag_test database.")
    store = Store(url)
    sources = [
        {"id": cid, "candidate_id": cid, "path": f"{cid}.docx", "name": "", "sha256": "test"}
        for cid in ["CAND-001", "CAND-002"]
    ]
    chunks = [
        {"id": cid + ":projects:1", "source_id": cid, "candidate_id": cid,
         "section": "Projects", "locator": "paragraph 1", "text": "Python API experience"}
        for cid in ["CAND-001", "CAND-002"]
    ]
    a = [1.0] + [0.0] * (DIMENSIONS - 1)
    b = [0.0, 1.0] + [0.0] * (DIMENSIONS - 2)
    try:
        store.replace(sources, chunks, [a, b])
        assert store.ready() == 2
        assert store.search(a, k=1)[0]["candidate_id"] == "CAND-001"
        assert store.search(a, "CAND-002", k=1)[0]["candidate_id"] == "CAND-002"
        store.replace(sources, chunks, [a, b])
        assert store.ready() == 2  # rerun is idempotent
        with pytest.raises(Exception):
            store.replace(sources, [chunks[0], chunks[0]], [a, b])
        assert store.ready() == 2  # duplicate insert rolled back the whole transaction
        with pytest.raises(ValueError):
            store.replace(sources, chunks, [a])
        assert store.ready() == 2
    finally:
        with store.connect() as conn:
            conn.execute("DELETE FROM chunks")
            conn.execute("DELETE FROM sources")
            conn.execute("DELETE FROM index_metadata")