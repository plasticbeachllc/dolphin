"""Factory for creating test backends with different configurations."""

from pathlib import Path
from typing import Optional, Dict, Any

from tests.kb_utils import InMemoryKBBackend


class TestBackendFactory:
    """Factory for creating test backends with different configurations."""

    @staticmethod
    def create_in_memory_backend(repo_path: Path, **kwargs) -> InMemoryKBBackend:
        """Create in-memory backend for fast testing.
        
        Args:
            repo_path: Path to the repository fixture
            **kwargs: Additional arguments for InMemoryKBBackend
                - repo_name: Name of the repository (default: "kb-fixture")
                - commit_sha: Commit SHA (default: "fixture-main")
        
        Returns:
            Configured InMemoryKBBackend instance
        """
        return InMemoryKBBackend(repo_path, **kwargs)
    
    @staticmethod  
    def create_lancedb_backend(temp_dir: Path, **kwargs) -> Any:
        """Create LanceDB backend with temporary storage.
        
        Args:
            temp_dir: Temporary directory for database storage
            **kwargs: Additional configuration for LanceDB backend
        
        Returns:
            LanceDBBackend instance or mock if dependencies not available
        """
        try:
            # Try to import and create actual LanceDB backend
            from kb.api.app import LanceDBBackend
            
            db_path = temp_dir / "test_lancedb"
            return LanceDBBackend(str(db_path), **kwargs)
        except ImportError:
            # Fallback to mock if LanceDB not available
            from tests.utils.mock_services import MockLanceDBBackend
            return MockLanceDBBackend(**kwargs)

    @staticmethod
    def create_test_config(
        repo_path: Path,
        backend_type: str = "memory",
        **backend_kwargs
    ) -> Dict[str, Any]:
        """Create a complete test configuration.
        
        Args:
            repo_path: Path to the repository
            backend_type: Type of backend ("memory" or "lancedb")
            **backend_kwargs: Additional backend configuration
        
        Returns:
            Dictionary with backend and configuration
        """
        if backend_type == "memory":
            backend = TestBackendFactory.create_in_memory_backend(
                repo_path, **backend_kwargs
            )
        elif backend_type == "lancedb":
            backend = TestBackendFactory.create_lancedb_backend(
                repo_path, **backend_kwargs
            )
        else:
            raise ValueError(f"Unknown backend type: {backend_type}")
        
        return {
            "backend": backend,
            "repo_path": repo_path,
            "backend_type": backend_type,
            "config": backend_kwargs
        }