#!/usr/bin/env python3
"""Test graph enrichment directly without MCP layer."""

import sys
from pathlib import Path

# Ensure repository root is on sys.path so local kb package resolves
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from kb.config import load_config
from kb.store.sqlite_meta import SQLiteMetadataStore
from kb.store.graph_store import GraphStore
from kb.retrieval.graph_context import GraphContextEnricher


def main():
    config = load_config()
    store_root = config.resolved_store_root()
    metadata_db = store_root / "metadata.db"

    print(f"📂 Using database: {metadata_db}")
    print(f"✓ Database exists: {metadata_db.exists()}")

    # Initialize stores
    sql_store = SQLiteMetadataStore(metadata_db)
    graph_store = GraphStore(metadata_db)

    # Initialize enricher
    enricher = GraphContextEnricher(
        graph_store=graph_store,
        sql_store=sql_store,
        max_related_nodes=10,
        max_edges_per_node=5,
    )

    print(f"\n✅ Enricher initialized: {enricher is not None}")
    print(f"✅ Graph store: {graph_store is not None}")
    print(f"✅ SQL store: {sql_store is not None}")

    # Create a mock search result for kb/api/search_backend.py lines 21-87
    mock_result = {
        "chunk_id": "test_chunk",
        "repo": "dolphin",
        "path": "kb/api/search_backend.py",
        "start_line": 21,
        "end_line": 87,
        "score": 0.95,
    }

    print("\n🔍 Testing enrichment with mock result:")
    print(f"   Path: {mock_result['path']}")
    print(f"   Lines: {mock_result['start_line']}-{mock_result['end_line']}")

    try:
        enriched = enricher.enrich_search_results(
            [mock_result],
            include_callsites=True,
            include_implementations=True,
            include_dependencies=True,
        )

        print("\n✅ Enrichment succeeded!")
        print(f"   Results count: {len(enriched)}")

        if enriched:
            result = enriched[0]
            has_graph = "graph_context" in result
            print(f"   Has graph_context: {has_graph}")

            if has_graph:
                gc = result["graph_context"]
                print("\n🎉 SUCCESS! Graph context found:")
                print(f"   Nodes: {len(gc.get('nodes', []))}")
                print(f"   Edges: {len(gc.get('edges', []))}")

                if gc.get("nodes"):
                    print("\n   Sample nodes:")
                    for node in gc["nodes"][:3]:
                        print(
                            f"      - {node.get('qualified_name')} ({node.get('kind')})"
                        )

                if gc.get("edges"):
                    print("\n   Sample edges:")
                    for edge in gc["edges"][:3]:
                        print(
                            f"      - {edge.get('relationship_type')}: {edge.get('source_name')} → {edge.get('target_name')}"
                        )
            else:
                print("\n❌ No graph_context in result")
                print(f"   Available keys: {list(result.keys())}")

    except Exception as e:
        print(f"\n❌ Enrichment failed: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
