#!/usr/bin/env python3
"""Clean up test repositories from the database.

This script removes test repositories that may have been left behind
from interrupted test runs. It's safe to run at any time.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from kb.config import CONFIG_ROOT
from kb.store.sqlite_meta import SQLiteMetadataStore


def cleanup_test_repos():
    """Remove all test repositories from the database."""
    db_path = CONFIG_ROOT / "metadata.db"
    
    if not db_path.exists():
        print(f"No database found at {db_path}")
        return
    
    print(f"Cleaning up test repositories from {db_path}")
    
    try:
        store = SQLiteMetadataStore(db_path)
        store.initialize()
        
        # Patterns to identify test repositories
        test_repo_patterns = [
            "test",
            "test_repo",
            "test-repo",
            "repo-1",
            "repo-2",
            "my-repo",
            "integration-test",
        ]
        
        with store._get_connection() as conn:
            cursor = conn.execute("SELECT id, name FROM repos")
            repos = cursor.fetchall()
            
            deleted_count = 0
            for repo_id, repo_name in repos:
                # Check if this looks like a test repository
                is_test_repo = any(
                    pattern in repo_name.lower() 
                    for pattern in test_repo_patterns
                )
                
                if is_test_repo:
                    print(f"  Deleting test repository: {repo_name} (id={repo_id})")
                    
                    # Delete all data associated with this repo
                    conn.execute("DELETE FROM chunks WHERE repo_id = ?", (repo_id,))
                    conn.execute("DELETE FROM files WHERE repo_id = ?", (repo_id,))
                    conn.execute("DELETE FROM scan_sessions WHERE repo_id = ?", (repo_id,))
                    conn.execute("DELETE FROM repos WHERE id = ?", (repo_id,))
                    
                    deleted_count += 1
            
            conn.commit()
            
        print(f"\nCleaned up {deleted_count} test repositories")
        
    except Exception as e:
        print(f"Error during cleanup: {e}", file=sys.stderr)
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(cleanup_test_repos())