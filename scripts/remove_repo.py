#!/usr/bin/env python3
"""Remove a repository from the knowledge store."""

from __future__ import annotations
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from kb.config import load_config
from kb.store import LanceDBStore, SQLiteMetadataStore


def remove_repo(repo_name: str) -> None:
    """Remove a repository and all its data from the knowledge store."""
    config = load_config()
    store_root = config.resolved_store_root()
    
    metadata = SQLiteMetadataStore(store_root / "metadata.db")
    metadata.initialize()
    
    lancedb = LanceDBStore(store_root / "lancedb")
    
    # Get repo info
    repo = metadata.get_repo_by_name(repo_name)
    if not repo:
        print(f"Repository '{repo_name}' not found.")
        return
    
    repo_id = int(repo["id"])
    
    # Delete from metadata database
    print(f"Removing metadata for '{repo_name}'...")
    with metadata._connect() as conn:
        cur = conn.cursor()
        
        # Get file IDs
        cur.execute("SELECT id FROM files WHERE repo_id = ?", (repo_id,))
        file_ids = [row[0] for row in cur.fetchall()]
        
        # Delete chunk locations for these files
        for file_id in file_ids:
            cur.execute("""
                DELETE FROM chunk_locations 
                WHERE content_id IN (
                    SELECT id FROM chunk_content WHERE file_id = ?
                )
            """, (file_id,))
        
        # Delete chunk content
        cur.execute("DELETE FROM chunk_content WHERE repo_id = ?", (repo_id,))
        
        # Delete from FTS
        cur.execute("DELETE FROM chunks_fts WHERE repo = ?", (repo_name,))
        
        # Delete files
        cur.execute("DELETE FROM files WHERE repo_id = ?", (repo_id,))
        
        # Delete sessions
        cur.execute("DELETE FROM sessions WHERE repo_id = ?", (repo_id,))
        
        # Delete repo
        cur.execute("DELETE FROM repos WHERE id = ?", (repo_id,))
        
        conn.commit()
    
    # Delete from LanceDB (both models)
    print(f"Removing vectors for '{repo_name}'...")
    for model in ["small", "large"]:
        try:
            lancedb.delete_repo(repo_name, model=model)
        except Exception as e:
            print(f"  Warning: Could not delete {model} vectors: {e}")
    
    print(f"✓ Repository '{repo_name}' removed successfully.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: uv run scripts/remove_repo.py <repo_name>")
        sys.exit(1)
    
    remove_repo(sys.argv[1])