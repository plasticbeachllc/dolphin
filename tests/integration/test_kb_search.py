"""Integration tests for KB search with provenance and snippet handling."""

from __future__ import annotations

from fastapi.testclient import TestClient

from kb.api.app import app
from kb.hashing import hash_text
from tests.kb_utils import FIXTURE_REPO_ROOT, kb_backend_context


def test_search_returns_provenance_rich_snippets():
    """Golden test verifying /v1/search returns provenance-rich snippets."""
    target_file = FIXTURE_REPO_ROOT / "src" / "widgets.py"
    expected_hash = hash_text(target_file.read_text(encoding="utf-8"))

    with kb_backend_context(commit_sha="abc12345") as _backend:
        client = TestClient(app)
        payload = {
            "query": "calibration metrics",
            "top_k": 3,
            "max_snippet_tokens": 12,
        }
        response = client.post("/search", json=payload)
        assert response.status_code == 200, f"Unexpected status: {response.status_code}"
        data = response.json()

        hits = data["hits"]
        assert len(hits) == 1, f"Expected one hit, received {len(hits)}"
        hit = hits[0]

        # Provenance and metadata checks.
        assert hit["repo"] == "kb-fixture"
        assert hit["path"] == "src/widgets.py"
        assert hit["provenance"]["commit"] == "abc12345"
        assert hit["provenance"]["text_hash"] == expected_hash

        # Snippet truncation and keyword presence.
        snippet_tokens = hit["snippet"].split()
        assert len(snippet_tokens) == 12, "Snippet should be truncated to 12 tokens"
        assert hit["snippet_tokens"] == 12
        assert hit["total_tokens"] > hit["snippet_tokens"]
        assert hit["truncated"] is True
        snippet_lc = hit["snippet"].lower()
        assert "calibration" in snippet_lc and "metrics" in snippet_lc, (
            "Snippet should retain the query terms"
        )

        # Meta payload echoes request parameters.
        assert data["meta"]["max_snippet_tokens"] == 12
        assert data["meta"]["top_k"] == 3
