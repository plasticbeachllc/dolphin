import shutil
import tempfile
import unittest
from pathlib import Path

from kb.retrieval.graph_context import GraphContextEnricher
from kb.store.graph_store import GraphStore
from kb.store.sqlite_meta import SQLiteMetadataStore


class TestGraphContextIntegration(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        # Use a single database file for both stores as they share tables (code_nodes, code_edges)
        self.db_path = Path(self.test_dir) / "knowledge.db"

        # Initialize metadata store and create tables
        self.sql_store = SQLiteMetadataStore(self.db_path)
        self.sql_store.initialize()

        # Initialize graph store pointing to the same DB
        self.graph_store = GraphStore(self.db_path)

        # Initialize enricher
        self.enricher = GraphContextEnricher(
            graph_store=self.graph_store,
            sql_store=self.sql_store,
            max_related_nodes=5,
            max_edges_per_node=5
        )

        # Setup base data
        self.setup_data()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def setup_data(self):
        # 1. Create Repo
        repo_path = Path(self.test_dir) / "test-repo"
        repo_path.mkdir()
        self.sql_store.register_repo(name="test-repo", path=repo_path)
        repo_info = self.sql_store.get_repo_by_name("test-repo")
        self.repo_id = repo_info["id"]

        # 2. Create File
        self.file_path = "src/main.py"
        self.file_id = self.sql_store.upsert_file(
            repo_id=self.repo_id,
            path=self.file_path,
            ext=".py",
            language="python",
            is_binary=False,
            size_bytes=100
        )

        # 3. Create Graph Nodes
        # Node 1: Function 'main'
        self.node1_id = self.graph_store.upsert_node(
            node_type="function",
            name="main",
            qualified_name="main",
            repo_id=self.repo_id,
            file_id=self.file_id,
            start_line=10,
            end_line=20,
            language="python",
            commit_sha="abc",
            branch="main",
            signature="def main():"
        )

        # Node 2: Function 'helper'
        self.node2_id = self.graph_store.upsert_node(
            node_type="function",
            name="helper",
            qualified_name="utils.helper",
            repo_id=self.repo_id,
            file_id=self.file_id,
            start_line=30,
            end_line=40,
            language="python",
            commit_sha="abc",
            branch="main",
            signature="def helper():"
        )

        # 4. Create Edge: main calls helper
        self.graph_store.upsert_edge(
            source_node_id=self.node1_id,
            target_node_id=self.node2_id,
            edge_type="calls",
            repo_id=self.repo_id,
            line_number=15,
            commit_sha="abc"
        )

    def test_enrich_with_real_db(self):
        """Test enrichment using a real SQLite database populated with data."""
        # Simulate a search result hitting the 'main' function
        results = [
            {
                "repo": "test-repo",
                "path": "src/main.py",
                "start_line": 12,
                "end_line": 15,
                "text": "calling helper()"
            }
        ]

        enriched = self.enricher.enrich_search_results(results)

        self.assertEqual(len(enriched), 1)
        self.assertIn("graph_context", enriched[0])
        context = enriched[0]["graph_context"]

        # Check Nodes
        nodes = context["nodes"]
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0]["name"], "main")
        self.assertEqual(nodes[0]["type"], "function")

        # Check Relationships
        rels = context["relationships"]
        self.assertEqual(len(rels), 1)
        rel = rels[0]
        self.assertEqual(rel["type"], "calls")
        self.assertEqual(rel["direction"], "outgoing")
        self.assertEqual(rel["target"]["name"], "helper")
        self.assertEqual(rel["line_number"], 15)

    def test_enrich_no_overlap(self):
        """Test search result that falls outside any graph node."""
        # Search result outside of any node
        results = [
            {
                "repo": "test-repo",
                "path": "src/main.py",
                "start_line": 100,
                "end_line": 110,
                "text": "some other code"
            }
        ]

        enriched = self.enricher.enrich_search_results(results)
        # Should not have graph_context
        self.assertNotIn("graph_context", enriched[0])

    def test_enrich_invalid_repo(self):
        """Test search result with non-existent repository."""
        results = [{"repo": "non-existent", "path": "src/main.py", "start_line": 10, "end_line": 20}]
        enriched = self.enricher.enrich_search_results(results)
        # Should handle gracefully and not crash
        self.assertNotIn("graph_context", enriched[0])
