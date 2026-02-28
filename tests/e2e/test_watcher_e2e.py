import os

# Port for E2E server
# Use dynamic port allocation to avoid conflicts in parallel execution
import socket
import subprocess
import time
from pathlib import Path

import pytest
import requests


def get_free_port():
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


@pytest.mark.e2e
def test_watcher_live_e2e(git_repo: Path, temp_db_path: Path, monkeypatch):
    """
    E2E test that runs the actual dolphin server with --watch logic.
    Verified by creating files and checking if they appear in the index (via DB).
    """

    # Get a dynamic free port
    e2e_port = get_free_port()
    e2e_host = "127.0.0.1"

    # 1. Setup Environment
    # Use a temp config file pointing to our temp DB and Repo
    store_root = temp_db_path.parent / "dolphin_store"
    store_root.mkdir(exist_ok=True)

    config_content = f"""
[storage]
store_root = "{store_root}"

[server]
endpoint = "{e2e_host}:{e2e_port}"

[embedding]
provider = "stub"
default_embed_model = "small"
"""
    config_path = store_root / "config.toml"
    config_path.write_text(config_content)

    env = os.environ.copy()
    env["DOLPHIN_CONFIG_PATH"] = str(config_path)
    env["DOLPHIN_API_KEY"] = "test-key"

    # 2. Add Repo via CLI (using subprocess)
    # This populates the DB with the repo
    subprocess.run(
        [
            "uv",
            "run",
            "dolphin",
            "add-repo",
            "test-repo",
            str(git_repo),
            "--no-index",
        ],
        env=env,
        check=True,
    )

    # 3. Start Server with --watch
    # We use subprocess to run "dolphin serve"
    server_process = subprocess.Popen(
        ["uv", "run", "dolphin", "serve", "--port", str(e2e_port), "--watch", "test-repo"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        # Wait for valid status
        base_url = f"http://{e2e_host}:{e2e_port}"
        assert wait_for_server(f"{base_url}/health"), "Server failed to start"

        # 4. Create a new file in the git repo (uncommitted)
        new_file = git_repo / "live_watch.py"
        new_file.write_text("def hello(): return 'world'")

        # 5. Wait for watcher to pick it up (debounce is 1.6s default)
        # We poll the DB

        # Connect to DB to verify
        # Note: metadata.db is in store_root/metadata.db
        metadata_db = store_root / "metadata.db"

        found = False
        start_wait = time.time()
        while time.time() - start_wait < 30:
            if metadata_db.exists():
                import sqlite3

                conn = sqlite3.connect(metadata_db)
                cur = conn.cursor()
                # Check files table
                try:
                    cur.execute("SELECT id FROM files WHERE path = ?", ("live_watch.py",))
                    if cur.fetchone():
                        found = True
                        break
                except Exception:
                    pass
                finally:
                    conn.close()
            time.sleep(0.5)

        assert found, "File 'live_watch.py' was not indexed by watcher within timeout"

        # 6. Branch Switch Test
        # Create a new branch, switch to it, add a file
        subprocess.run(["git", "-C", str(git_repo), "checkout", "-b", "feature-branch"], check=True)

        # IMPORTANT: Wait for branch reconciliation to complete
        # The watcher detects branch switches and triggers reconcile_branch_switch
        # which can take time. We need to wait for that to finish before creating
        # new files, otherwise we race with the reconciliation process.
        time.sleep(3.0)  # Give reconciliation time to complete

        branch_file = git_repo / "branch_file.py"
        branch_file.write_text("x = 42")

        # Wait for index with more aggressive polling
        found_branch = False
        start_wait = time.time()
        poll_interval = 0.3  # Poll more frequently
        max_wait = 30

        while time.time() - start_wait < max_wait:
            import sqlite3

            conn = sqlite3.connect(metadata_db)
            cur = conn.cursor()
            try:
                cur.execute("SELECT id FROM files WHERE path = ?", ("branch_file.py",))
                if cur.fetchone():
                    found_branch = True
                    break
            except Exception as e:
                # Log exception for debugging
                print(f"Warning: DB query failed: {e}")
            finally:
                conn.close()
            time.sleep(poll_interval)

        if not found_branch:
            # Enhanced error message with more context
            elapsed = time.time() - start_wait
            print(f"Branch file not found after {elapsed:.1f}s of waiting")
            # Check if the file exists on disk
            print(f"File exists on disk: {branch_file.exists()}")
            # Query all files in the DB for debugging
            conn = sqlite3.connect(metadata_db)
            cur = conn.cursor()
            cur.execute("SELECT path FROM files ORDER BY path")
            all_files = [row[0] for row in cur.fetchall()]
            conn.close()
            print(f"All files in DB ({len(all_files)}): {all_files[:20]}")  # Show first 20

        assert found_branch, "File 'branch_file.py' from new branch was not indexed"

    finally:
        # Cleanup
        server_process.terminate()
        try:
            server_process.wait(timeout=5)
        except TimeoutError:
            server_process.kill()

        # Print server output if failed
        if server_process.returncode != 0 and server_process.returncode != -15:  # -15 is SIGTERM
            stdout, stderr = server_process.communicate()
            print("Server Stdout:", stdout)
            print("Server Stderr:", stderr)
