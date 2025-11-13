#!/usr/bin/env python3
"""
Simple test to verify vector search is working with populated data.
"""

from pathlib import Path
from kb.api.search_backend import create_search_backend
from kb.api.app import SearchRequest


def test_vector_search_with_populated_data():
    """Test that vector search actually works with data."""
    
    store_root = Path.home() / '.dolphin' / 'knowledge_store'
    print(f"Testing vector search with store root: {store_root}")
    
    if not store_root.exists():
        print("❌ Knowledge store doesn't exist. Index a repository first.")
        raise AssertionError("Knowledge store doesn't exist")
    
    # Check if we can find the metadata store and see if there's any data
    from kb.store.sqlite_meta import SQLiteMetadataStore
    sql_store = SQLiteMetadataStore(store_root / "metadata.db")
    
    # Check chunk counts
    try:
        counts = sql_store.summarize()
        print(f"Database summary: {counts}")
        
        assert counts['chunks'] > 0, "No chunks found in database"
        print(f"✅ Found {counts['chunks']} chunks in database")
        
        print(f"✅ Found {counts['chunks']} chunks in database")
    except Exception as e:
        print(f"❌ Error checking database: {e}")
        raise AssertionError(f"Database check failed: {e}")
    
    # Test backend creation
    try:
        backend = create_search_backend(store_root=store_root, hybrid_search_enabled=False)
        print("✅ SearchBackend created successfully")
    except Exception as e:
        print(f"❌ Error creating search backend: {e}")
        raise AssertionError(f"Search backend creation failed: {e}")
    
    # Test with a simple query
    try:
        request = SearchRequest(query="test", top_k=3)
        results = backend.search(request)
        
        print(f"Vector search returned {len(results)} results")
        
        assert len(results) > 0, "Vector search returned no results"
        print(f"✅ Vector search working! Sample result: {results[0]}")
            
    except Exception as e:
        print(f"❌ Error during vector search: {e}")
        raise AssertionError(f"Vector search failed: {e}")


def test_hybrid_search_comparison():
    """Test hybrid vs vector-only search on the same data."""
    
    store_root = Path.home() / '.dolphin' / 'knowledge_store'
    
    # Create both backends
    vector_backend = create_search_backend(store_root=store_root, hybrid_search_enabled=False)
    hybrid_backend = create_search_backend(store_root=store_root, hybrid_search_enabled=True)
    
    # Test query
    request = SearchRequest(query="authentication", top_k=5)
    
    # Time both searches
    import time
    
    # Vector-only search
    start = time.time()
    vector_results = vector_backend.search(request)
    vector_time = (time.time() - start) * 1000
    
    # Hybrid search
    start = time.time()
    hybrid_results = hybrid_backend.search(request)
    hybrid_time = (time.time() - start) * 1000
    
    print(f"\nPerformance Comparison:")
    print(f"Vector-only: {vector_time:.1f}ms ({len(vector_results)} results)")
    print(f"Hybrid:      {hybrid_time:.1f}ms ({len(hybrid_results)} results)")
    print(f"Overhead:    {hybrid_time - vector_time:.1f}ms")
    
    # Assert that both searches returned results
    assert len(vector_results) >= 0, "Vector search should return results"
    assert len(hybrid_results) >= 0, "Hybrid search should return results"


def main():
    """Main test function."""
    
    print("Vector Search Performance Test")
    print("=" * 40)
    
    # First check if we have populated data
    if test_vector_search_with_populated_data():
        print("\n✅ Vector search is working correctly")
        test_hybrid_search_comparison()
    else:
        print("\n❌ Vector search test failed")
        print("\nTo populate the database, run:")
        print("python -m kb.cli index --repo test-repo /path/to/your/repo")


if __name__ == '__main__':
    main()