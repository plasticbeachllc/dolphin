import os
import subprocess
import time
from pathlib import Path

import pytest
import requests

# Port for E2E server
E2E_PORT = 7779
E2E_HOST = "127.0.0.1"


def wait_for_server(url: str, timeout: int = 10) -> bool:
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

    # 1. Setup Environment
    # Use a temp config file pointing to our temp DB and Repo
    store_root = temp_db_path.parent / "dolphin_store"
    store_root.mkdir(exist_ok=True)

    config_content = f"""
[storage]
store_root = "{store_root}"

[server]
endpoint = "{E2E_HOST}:{E2E_PORT}"

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
        ["dolphin", "kb", "add-repo", "test-repo", str(git_repo), "--default-embed-model", "small"], env=env, check=True
    )

    # 3. Start Server with --watch
    # We use subprocess to run "dolphin serve"
    server_process = subprocess.Popen(
        ["dolphin", "serve", "--port", str(E2E_PORT), "--watch", "test-repo"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        # Wait for valid status
        base_url = f"http://{E2E_HOST}:{E2E_PORT}"
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
        while time.time() - start_wait < 10:
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

        branch_file = git_repo / "branch_file.py"
        branch_file.write_text("x = 42")

        # Wait for index
        found_branch = False
        start_wait = time.time()
        while time.time() - start_wait < 10:
            import sqlite3

            conn = sqlite3.connect(metadata_db)
            cur = conn.cursor()
            try:
                cur.execute("SELECT id FROM files WHERE path = ?", ("branch_file.py",))
                if cur.fetchone():
                    found_branch = True
                    break
            except Exception:
                pass
            finally:
                conn.close()
            time.sleep(0.5)

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
