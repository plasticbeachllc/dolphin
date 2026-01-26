import os
import socket
import sqlite3
import subprocess
import time
from pathlib import Path
from typing import Generator, Tuple

import pytest
import requests

# Constants
SERVER_HOST = "127.0.0.1"


def get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def wait_for_server(url: str, timeout: int = 15) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        try:
            requests.get(url)
            return True
        except requests.ConnectionError:
            time.sleep(0.5)
    return False


def wait_for_api_result(base_url: str, query: str, filename: str, timeout: int = 15) -> bool:
    """Poll API until the filename appears in results."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = requests.post(
                f"{base_url}/v1/search",
                json={"query": query, "repos": ["test-repo"]},
                headers={"X-API-Key": "test-key"}
            )
            if resp.status_code == 200:
                results = resp.json().get("results", [])
                if any(filename in r.get("path", "") for r in results):
                    return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


@pytest.mark.e2e
class TestWatcherComprehensive:
    @pytest.fixture(scope="function")
    def server_setup(self, git_repo: Path, temp_db_path: Path) -> Generator[Tuple[str, Path, Path], None, None]:
        """
        Setup a fresh dolphin server watching a fresh git repo for each test.
        Returns: (base_url, repo_path, store_root)
        """
        # Dynamic port
        port = get_free_port()

        # Config setup
        store_root = temp_db_path.parent / f"dolphin_store_{port}"
        store_root.mkdir(exist_ok=True)

        config_content = f"""
[storage]
store_root = "{store_root}"

[server]
endpoint = "{SERVER_HOST}:{port}"

[embedding]
provider = "stub"
default_embed_model = "small"
"""
        config_path = store_root / "config.toml"
        config_path.write_text(config_content)

        env = os.environ.copy()
        env["DOLPHIN_CONFIG_PATH"] = str(config_path)
        env["DOLPHIN_API_KEY"] = "test-key"

        # Add Repo
        subprocess.run(
            [
                "dolphin",
                "kb",
                "add-repo",
                "test-repo",
                str(git_repo),
                "--no-index",
            ],
            env=env,
            check=True,
            capture_output=True,
        )

        # Start Server
        server_process = subprocess.Popen(
            ["dolphin", "serve", "--port", str(port), "--watch", "test-repo"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        base_url = f"http://{SERVER_HOST}:{port}"

        try:
            assert wait_for_server(f"{base_url}/health"), "Server failed to start"
            yield base_url, git_repo, store_root
        finally:
            server_process.terminate()
            try:
                server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server_process.kill()
            
            # Print logs on failure (can be inspected if test fails)
            if server_process.returncode not in (0, -15):
                stdout, stderr = server_process.communicate()
                print(f"Server Stdout:\n{stdout}")
                print(f"Server Stderr:\n{stderr}")

    def _wait_for_file_in_db(self, store_root: Path, file_path: str, timeout: int = 10) -> bool:
        """Helper to wait for a file to appear in the DB."""
        db_path = store_root / "metadata.db"
        start = time.time()
        while time.time() - start < timeout:
            if db_path.exists():
                try:
                    conn = sqlite3.connect(db_path)
                    cur = conn.cursor()
                    cur.execute("SELECT id FROM files WHERE path = ?", (file_path,))
                    result = cur.fetchone()
                    conn.close()
                    if result:
                        return True
                except sqlite3.Error:
                    pass
            time.sleep(0.2)
        return False

    def _wait_for_file_gone_from_db(self, store_root: Path, file_path: str, timeout: int = 10) -> bool:
        """Helper to wait for a file to disappear from the DB."""
        db_path = store_root / "metadata.db"
        start = time.time()
        while time.time() - start < timeout:
            if db_path.exists():
                try:
                    conn = sqlite3.connect(db_path)
                    cur = conn.cursor()
                    cur.execute("SELECT id FROM files WHERE path = ?", (file_path,))
                    result = cur.fetchone()
                    conn.close()
                    if not result:
                        return True
                except sqlite3.Error:
                    pass
            time.sleep(0.2)
        return False

    def test_create_and_search(self, server_setup):
        """Test file creation is detected and indexed."""
        base_url, repo_path, store_root = server_setup
        
        # Create file
        filename = "unique_msg.txt"
        unique_content = "banana_stand_money"
        (repo_path / filename).write_text(unique_content)

        # Wait for DB index
        assert self._wait_for_file_in_db(store_root, filename), f"File {filename} not indexed"

        # Verify via API (Search) - Poll for result
        found = wait_for_api_result(base_url, "banana_stand", filename)
        assert found, f"API did not return {filename} for query 'banana_stand'"

    def test_modify_file(self, server_setup):
        """Test file modification is detected and re-indexed."""
        base_url, repo_path, store_root = server_setup

        filename = "mod.py"
        (repo_path / filename).write_text("def foo(): return 'version_one'")

        assert self._wait_for_file_in_db(store_root, filename), "Initial file not indexed"

        # Modify file
        time.sleep(1)  # Ensure mtime changes significantly for some filesystems
        (repo_path / filename).write_text("def foo(): return 'version_two'")

        # We can't easily check DB for content update without inspecting chunks,
        # but we can check if the API returns the new content.
        # Wait a bit for the watcher to pick it up and index
        found = wait_for_api_result(base_url, "version_two", filename)
        assert found, "API did not find updated content 'version_two'"

    def test_delete_file(self, server_setup):
        """Test file deletion is detected and removed from index."""
        _, repo_path, store_root = server_setup

        filename = "del.py"
        (repo_path / filename).write_text("print('delete me')")

        assert self._wait_for_file_in_db(store_root, filename), "File not indexed initially"

        # Delete
        (repo_path / filename).unlink()

        # Verify removal
        assert self._wait_for_file_gone_from_db(store_root, filename), f"File {filename} not removed from DB"

    def test_rename_file(self, server_setup):
        """Test renaming a file updates the index (delete old, add new)."""
        _, repo_path, store_root = server_setup

        old_name = "old_name.py"
        new_name = "new_name.py"
        (repo_path / old_name).write_text("print('renamed')")

        assert self._wait_for_file_in_db(store_root, old_name), "Old file not indexed"

        # Rename
        (repo_path / old_name).rename(repo_path / new_name)

        # Verify old gone, new present
        assert self._wait_for_file_gone_from_db(store_root, old_name), "Old file not removed"
        assert self._wait_for_file_in_db(store_root, new_name), "New file not indexed"

    def test_ignored_file_at_startup(self, git_repo, temp_db_path):
        """Test that ignored files are NOT indexed when present at startup."""
        # 1. Setup Repo content BEFORE server start
        (git_repo / ".gitignore").write_text("*.ignored")
        (git_repo / "control.txt").write_text("control")
        ignored_file = "secret.ignored"
        (git_repo / ignored_file).write_text("secret")

        # 2. Setup Config (Manual setup similar to fixture)
        port = get_free_port()
        store_root = temp_db_path.parent / f"dolphin_store_{port}"
        store_root.mkdir(exist_ok=True)
        config_content = f"""
[storage]
store_root = "{store_root}"
[server]
endpoint = "{SERVER_HOST}:{port}"
[embedding]
provider = "stub"
"""
        config_path = store_root / "config.toml"
        config_path.write_text(config_content)
        env = os.environ.copy()
        env["DOLPHIN_CONFIG_PATH"] = str(config_path)
        env["DOLPHIN_API_KEY"] = "test-key"

        # 3. Add Repo
        subprocess.run(
            ["dolphin", "kb", "add-repo", "test-repo", str(git_repo), "--no-index"],
            env=env,
            check=True,
            capture_output=True
        )

        # 4. Start Server
        server_process = subprocess.Popen(
            ["dolphin", "serve", "--port", str(port), "--watch", "test-repo"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        try:
            base_url = f"http://{SERVER_HOST}:{port}"
            assert wait_for_server(f"{base_url}/health"), "Server failed to start"
            
            # Wait for control file
            assert self._wait_for_file_in_db(store_root, "control.txt"), "Control file not indexed"

            # Verify ignored file NOT in DB
            assert not self._wait_for_file_in_db(store_root, ignored_file, timeout=2), \
                f"Ignored file {ignored_file} WAS indexed (startup check)"
        finally:
            server_process.terminate()
            try:
                server_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server_process.kill()

    def test_nested_creation(self, server_setup):
        """Test creating files in subdirectories."""
        _, repo_path, store_root = server_setup

        nested_dir = repo_path / "src" / "components"
        nested_dir.mkdir(parents=True)
        filename = "src/components/Button.tsx"
        (repo_path / filename).write_text("export const Button = () => {}")

        assert self._wait_for_file_in_db(store_root, filename), f"Nested file {filename} not indexed"
