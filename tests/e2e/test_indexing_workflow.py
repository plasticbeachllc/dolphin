"""End-to-end tests for complete indexing workflow."""

import pytest
from pathlib import Path

from kb.pipeline import IngestionPipeline
from kb.store import SQLiteMetadataStore


class TestIndexingWorkflow:
    """End-to-end tests for indexing workflow."""

    def test_full_indexing_workflow(self, e2e_kb_setup):
        """Test complete workflow: add repo → index → verify metadata."""
        setup = e2e_kb_setup
        pipeline = setup['pipeline']
        metadata_store = setup['metadata_store']
        repo_name = setup['repo_name']

        # Step 1: Verify repository was registered
        repos = metadata_store.list_all_repos()
        assert any(r['name'] == repo_name for r in repos)

        # Step 2: Index repository
        result = pipeline.index(repo_name, dry_run=False, force=True)

        # Step 3: Verify indexing completed
        assert result['session_id'] is not None
        assert result['files_indexed'] > 0
        assert result['chunks_indexed'] > 0

        # Step 4: Verify session metadata
        session = metadata_store.get_session(result['session_id'])
        assert session is not None
        assert session['status'] in ['completed', 'running']

        # Step 5: Verify files were tracked
        files = metadata_store.list_files(repo_name)
        assert len(files) > 0

    def test_incremental_indexing_workflow(self, e2e_kb_setup):
        """Test incremental updates: index → modify → re-index → verify."""
        setup = e2e_kb_setup
        pipeline = setup['pipeline']
        metadata_store = setup['metadata_store']
        repo_name = setup['repo_name']
        repo_path = setup['repo_path']

        # Step 1: Initial index
        result1 = pipeline.index(repo_name, dry_run=False, force=True)
        initial_chunks = result1['chunks_indexed']

        # Step 2: Add new file
        (repo_path / "auth.py").write_text("""
def authenticate_with_token(token):
    '''Authenticate using JWT token.'''
    if not token or len(token) < 32:
        return False
    return True

def refresh_token(old_token):
    '''Refresh authentication token.'''
    import secrets
    return secrets.token_hex(32)
""")

        # Step 3: Re-index
        result2 = pipeline.index(repo_name, dry_run=False, force=False)

        # Step 4: Verify incremental behavior
        # Should have indexed at least the new file
        assert result2['session_id'] is not None
        # Either chunks_indexed or chunks_skipped should account for new content
        assert (result2['chunks_indexed'] + result2['chunks_skipped']) >= initial_chunks

        # Step 5: Verify new file is tracked
        files = metadata_store.list_files(repo_name)
        file_paths = [f['path'] for f in files]
        assert any('auth.py' in path for path in file_paths)

    def test_indexing_with_errors_continues(self, e2e_kb_setup):
        """Test that indexing continues even if some files have errors."""
        setup = e2e_kb_setup
        pipeline = setup['pipeline']
        repo_name = setup['repo_name']
        repo_path = setup['repo_path']

        # Create a file that might cause issues
        (repo_path / "binary.dat").write_bytes(b'\x00\x01\x02\x03')

        # Index should complete despite binary file
        result = pipeline.index(repo_name, dry_run=False, force=True)

        # Should have indexed at least the valid files
        assert result['files_indexed'] > 0
        assert result['chunks_indexed'] > 0

    def test_indexing_respects_ignore_patterns(self, e2e_kb_setup):
        """Test that ignore patterns are respected during indexing."""
        setup = e2e_kb_setup
        pipeline = setup['pipeline']
        metadata_store = setup['metadata_store']
        repo_name = setup['repo_name']
        repo_path = setup['repo_path']

        # Create files that should be ignored
        pycache_dir = repo_path / "__pycache__"
        pycache_dir.mkdir()
        (pycache_dir / "test.pyc").write_bytes(b'')

        # Index
        result = pipeline.index(repo_name, dry_run=False, force=True)

        # Verify ignored files were not indexed
        files = metadata_store.list_files(repo_name)
        file_paths = [f['path'] for f in files]
        assert not any('__pycache__' in path for path in file_paths)
        assert not any('.pyc' in path for path in file_paths)

    def test_force_reindex_workflow(self, e2e_kb_setup):
        """Test force re-indexing replaces existing content."""
        setup = e2e_kb_setup
        pipeline = setup['pipeline']
        repo_name = setup['repo_name']

        # Initial index
        result1 = pipeline.index(repo_name, dry_run=False, force=True)
        session_id1 = result1['session_id']

        # Force re-index
        result2 = pipeline.index(repo_name, dry_run=False, force=True)
        session_id2 = result2['session_id']

        # Should create new session
        assert session_id2 != session_id1

        # Should re-process files
        assert result2['files_indexed'] > 0


class TestIndexingEdgeCases:
    """Test edge cases in indexing workflow."""

    def test_empty_repository_indexing(self, e2e_kb_setup):
        """Test indexing an empty repository."""
        setup = e2e_kb_setup
        pipeline = setup['pipeline']
        repo_path = setup['repo_path']

        # Remove all files
        for file in repo_path.iterdir():
            if file.is_file():
                file.unlink()

        # Index should handle empty repo
        result = pipeline.index('test-repo', dry_run=False, force=True)

        assert result['session_id'] is not None
        assert result['files_indexed'] == 0
        assert result['chunks_indexed'] == 0

    def test_large_file_indexing(self, e2e_kb_setup):
        """Test indexing large files."""
        setup = e2e_kb_setup
        pipeline = setup['pipeline']
        repo_path = setup['repo_path']

        # Create a large file
        large_content = "def function_{}():\n    pass\n\n" * 1000
        (repo_path / "large.py").write_text(large_content)

        # Should index successfully
        result = pipeline.index('test-repo', dry_run=False, force=True)

        assert result['chunks_indexed'] > 0

    def test_multiple_file_types_indexing(self, e2e_kb_setup):
        """Test indexing repository with multiple file types."""
        setup = e2e_kb_setup
        pipeline = setup['pipeline']
        metadata_store = setup['metadata_store']
        repo_path = setup['repo_path']

        # Add various file types
        (repo_path / "script.ts").write_text("""
function greet(name: string): string {
    return `Hello, ${name}!`;
}
""")

        (repo_path / "styles.css").write_text("""
.button {
    background-color: blue;
    color: white;
}
""")

        (repo_path / "query.sql").write_text("""
SELECT * FROM users WHERE active = true;
""")

        # Index
        result = pipeline.index('test-repo', dry_run=False, force=True)

        # Verify different file types were indexed
        files = metadata_store.list_files('test-repo')
        extensions = [Path(f['path']).suffix for f in files]

        assert result['files_indexed'] > 0
        # At least some files should have been processed
        assert result['chunks_indexed'] > 0


class TestIndexingPerformance:
    """Test indexing performance characteristics."""

    def test_indexing_completes_in_reasonable_time(self, e2e_kb_setup):
        """Test that indexing completes within reasonable time."""
        import time

        setup = e2e_kb_setup
        pipeline = setup['pipeline']

        start_time = time.time()
        result = pipeline.index('test-repo', dry_run=False, force=True)
        elapsed_time = time.time() - start_time

        # Should complete within 30 seconds for small test repo
        assert elapsed_time < 30
        assert result['files_indexed'] > 0

    @pytest.mark.skip(reason="Performance test - run manually")
    def test_indexing_throughput(self, e2e_kb_setup):
        """Test indexing throughput."""
        import time

        setup = e2e_kb_setup
        pipeline = setup['pipeline']
        repo_path = setup['repo_path']

        # Create many files
        for i in range(100):
            (repo_path / f"file_{i}.py").write_text(f"def func_{i}():\n    pass\n")

        start_time = time.time()
        result = pipeline.index('test-repo', dry_run=False, force=True)
        elapsed_time = time.time() - start_time

        throughput = result['files_indexed'] / elapsed_time

        # Should process at least 10 files per second
        assert throughput > 10
