"""Unit tests for parallel file scanner."""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from kb.ingest.parallel_scanner import _process_file_batch, scan_repo_parallel
from kb.ingest.scanner import FileCandidate


class TestProcessFileBatch:
    """Unit tests for _process_file_batch function."""

    def test_process_empty_batch(self, tmp_path):
        """Test processing an empty batch."""
        result = _process_file_batch([], tmp_path, [], [])
        assert result == []

    def test_process_batch_skips_submodules(self, tmp_path):
        """Test that submodule files are skipped."""
        # Create a test file
        test_file = tmp_path / "submodule" / "file.py"
        test_file.parent.mkdir()
        test_file.write_text("print('hello')")

        result = _process_file_batch(
            ["submodule/file.py"],
            tmp_path,
            ["submodule/"],  # Submodule prefix
            [],
        )

        assert len(result) == 0

    def test_process_batch_skips_binary_files(self, tmp_path):
        """Test that binary files are skipped."""
        # Create a binary file
        binary_file = tmp_path / "test.bin"
        binary_file.write_bytes(b"\x00\x01\x02\x03")

        result = _process_file_batch(
            ["test.bin"],
            tmp_path,
            [],
            [],
        )

        assert len(result) == 0

    def test_process_batch_includes_valid_files(self, tmp_path):
        """Test that valid files are included."""
        # Create a valid Python file
        py_file = tmp_path / "test.py"
        py_file.write_text("print('hello')")

        result = _process_file_batch(
            ["test.py"],
            tmp_path,
            [],
            [],
        )

        assert len(result) == 1
        assert result[0].rel_path == "test.py"
        assert result[0].language == "python"


class TestScanRepoParallel:
    """Unit tests for scan_repo_parallel function."""

    def test_scan_non_git_repo_raises_error(self, tmp_path):
        """Test that scanning non-git repo raises ScannerError."""
        from kb.ingest.scanner import ScannerError

        with pytest.raises(ScannerError):
            scan_repo_parallel(tmp_path, [])

    def test_scan_empty_repo(self, tmp_path):
        """Test scanning an empty git repository."""
        # Create a git repo
        (tmp_path / ".git").mkdir()

        with patch("kb.ingest.scanner._list_tracked", return_value=[]):
            result = scan_repo_parallel(tmp_path, [])
            assert result == []

    def test_scan_small_repo_uses_sequential(self, tmp_path):
        """Test that small repos use sequential scanning."""
        import subprocess

        # Initialize git repo properly
        (tmp_path / ".git").mkdir()
        subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)

        # Create a small number of files
        for i in range(5):
            (tmp_path / f"file{i}.py").write_text(f"# File {i}")

        with patch("kb.ingest.scanner.scan_repo") as mock_scan:
            mock_scan.return_value = []

            # Should fall back to sequential for small repos
            scan_repo_parallel(tmp_path, [], batch_size=100)

            # Sequential scan should be called
            mock_scan.assert_called_once()

    def test_scan_respects_num_workers(self, tmp_path):
        """Test that num_workers parameter is respected."""
        (tmp_path / ".git").mkdir()

        # Create enough files for parallel processing
        for i in range(250):
            (tmp_path / f"file{i}.py").write_text(f"# File {i}")

        with patch("kb.ingest.scanner._list_tracked") as mock_list:
            mock_list.return_value = [f"file{i}.py" for i in range(250)]

            with patch("multiprocessing.Pool") as mock_pool:
                mock_pool.return_value.__enter__.return_value.imap_unordered.return_value = (
                    []
                )

                scan_repo_parallel(tmp_path, [], num_workers=4)

                # Pool should be created with specified workers
                mock_pool.assert_called_once()
                assert mock_pool.call_args[1]["processes"] == 4

    def test_scan_fallback_on_error(self, tmp_path):
        """Test fallback to sequential on error."""
        (tmp_path / ".git").mkdir()

        for i in range(250):
            (tmp_path / f"file{i}.py").write_text(f"# File {i}")

        with patch("kb.ingest.scanner._list_tracked") as mock_list:
            mock_list.return_value = [f"file{i}.py" for i in range(250)]

            with patch("multiprocessing.Pool") as mock_pool:
                # Simulate error in parallel processing
                mock_pool.return_value.__enter__.return_value.imap_unordered.side_effect = RuntimeError(
                    "Test error"
                )

                with patch("kb.ingest.scanner.scan_repo") as mock_sequential:
                    mock_sequential.return_value = []

                    scan_repo_parallel(tmp_path, [])

                    # Should fall back to sequential
                    mock_sequential.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
