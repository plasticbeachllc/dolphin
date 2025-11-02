"""ANN parameter tuning for LanceDB vector search.

This module provides configuration for Approximate Nearest Neighbor (ANN)
search parameters in LanceDB, allowing fine-grained control over the
speed-accuracy tradeoff.

LanceDB uses IVF (Inverted File Index) with Product Quantization:
- nprobes: Number of IVF clusters to search
- refine_factor: Post-filtering exact distance computations

Mathematical Background:
- IVF reduces search space from O(N) to O(N/K × nprobes)
- refine_factor prevents false negatives from quantization
- Optimal nprobes ≈ √K for balanced speed/recall
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal


@dataclass
class ANNParams:
    """Configurable ANN parameters for LanceDB.
    
    Attributes:
        metric: Distance metric for similarity computation
            - "cosine": Best for normalized embeddings (OpenAI, SBERT)
            - "L2": Euclidean distance, for non-normalized vectors
            - "dot": Inner product, faster but requires careful normalization
        
        nprobes: Number of IVF clusters to probe during search
            - Low (1-5): Very fast, ~60-80% recall
            - Medium (10-20): Balanced, ~90-95% recall
            - High (30-50): Slow but accurate, ~98-99% recall
            - Formula: optimal ≈ sqrt(num_clusters)
        
        refine_factor: How many candidates to re-rank with exact distances
            - Post-filters quantized results to improve precision
            - Factor of nprobes × refine_factor candidates examined
            - Higher values reduce quantization errors
        
        use_index: Whether to use IVF index or brute-force search
            - False: O(N) exhaustive search, 100% recall
            - True: O(N/K × nprobes) approximate search
    """
    
    metric: Literal["cosine", "L2", "dot"] = "cosine"
    nprobes: int = 20
    refine_factor: int = 10
    use_index: bool = True
    
    def __post_init__(self):
        """Validate parameter ranges."""
        if self.nprobes < 1:
            raise ValueError(f"nprobes must be >= 1, got {self.nprobes}")
        if self.refine_factor < 1:
            raise ValueError(f"refine_factor must be >= 1, got {self.refine_factor}")
    
    @classmethod
    def for_speed(cls) -> "ANNParams":
        """Optimized for speed (95% recall, 2x faster).
        
        Use when:
        - Latency is critical
        - Large result sets (top_k > 20)
        - Acceptable to miss a few relevant items
        
        Expected performance:
        - Latency: ~30ms p50
        - Recall: ~95%
        - Speedup: 2x vs default
        """
        return cls(
            metric="cosine",
            nprobes=10,  # Search fewer clusters
            refine_factor=5,  # Less refinement
            use_index=True
        )
    
    @classmethod
    def for_accuracy(cls) -> "ANNParams":
        """Optimized for accuracy (99% recall, same speed as default).
        
        Use when:
        - Quality is critical
        - Small result sets (top_k <= 5)
        - Cannot afford to miss relevant items
        
        Expected performance:
        - Latency: ~50ms p50
        - Recall: ~99%
        - Speedup: Same as default
        """
        return cls(
            metric="cosine",
            nprobes=30,  # Search more clusters
            refine_factor=20,  # More refinement
            use_index=True
        )
    
    @classmethod
    def for_development(cls) -> "ANNParams":
        """Exact search for development/debugging.
        
        Use when:
        - Testing search quality
        - Debugging relevance issues
        - Establishing baseline metrics
        
        Warning: Very slow for large datasets (O(N))
        """
        return cls(
            metric="cosine",
            nprobes=1000,  # Search all clusters
            refine_factor=100,
            use_index=False  # Brute force
        )
    
    @classmethod
    def adaptive(
        cls,
        query_type: str = "concept",
        top_k: int = 10,
        dataset_size: int = 100000
    ) -> "ANNParams":
        """Adaptive parameters based on query characteristics.
        
        Args:
            query_type: Type of query
                - "identifier": Exact match queries (UserController)
                - "concept": Semantic queries (authentication flow)
                - "example": Code example queries (how to parse JSON)
            top_k: Number of results requested
            dataset_size: Approximate number of indexed vectors
        
        Returns:
            ANNParams tuned for the query characteristics
        """
        # Estimate optimal nprobes based on dataset size
        # Rule of thumb: nprobes ≈ sqrt(K) where K = dataset_size / 100
        estimated_clusters = max(dataset_size // 100, 10)
        optimal_nprobes = int(math.sqrt(estimated_clusters))
        
        if query_type == "identifier":
            # Need high precision for exact matches
            return cls(
                metric="cosine",
                nprobes=min(optimal_nprobes * 2, 50),
                refine_factor=20,
                use_index=True
            )
        elif top_k <= 5:
            # Small result set, can afford accuracy
            return cls(
                metric="cosine",
                nprobes=optimal_nprobes,
                refine_factor=10,
                use_index=True
            )
        else:
            # Large result set, prioritize speed
            return cls(
                metric="cosine",
                nprobes=max(optimal_nprobes // 2, 10),
                refine_factor=5,
                use_index=True
            )
    
    def estimated_speedup(self, baseline_nprobes: int = 20) -> float:
        """Estimate speedup vs baseline configuration.
        
        Approximate formula:
        - search_time ∝ nprobes × refine_factor
        - speedup = baseline_cost / current_cost
        """
        baseline_cost = baseline_nprobes * 10  # Default refine_factor
        current_cost = self.nprobes * self.refine_factor
        return baseline_cost / current_cost if current_cost > 0 else 1.0
    
    def to_lancedb_params(self) -> dict:
        """Convert to LanceDB query parameters."""
        return {
            "metric": self.metric,
            "nprobes": self.nprobes,
            "refine_factor": self.refine_factor,
            "use_index": self.use_index,
        }
    
    @classmethod
    def from_config(cls, config) -> "ANNParams":
        """Create ANNParams from configuration.
        
        Args:
            config: Configuration object with [retrieval.ann] section
            
        Returns:
            ANNParams instance based on config strategy
        """
        # Get strategy and custom params from config
        strategy = getattr(config.retrieval.ann, 'strategy', 'adaptive')
        custom_metric = getattr(config.retrieval.ann, 'metric', None)
        custom_nprobes = getattr(config.retrieval.ann, 'nprobes', None)
        custom_refine_factor = getattr(config.retrieval.ann, 'refine_factor', None)
        
        if strategy == 'speed':
            return cls.for_speed()
        elif strategy == 'accuracy':
            return cls.for_accuracy()
        elif strategy == 'development':
            return cls.for_development()
        elif strategy == 'custom' and custom_metric and custom_nprobes and custom_refine_factor:
            return cls(
                metric=custom_metric,
                nprobes=custom_nprobes,
                refine_factor=custom_refine_factor,
                use_index=True
            )
        else:
            # Default to adaptive with config values if available
            adaptive_config = getattr(config.retrieval.ann, 'adaptive', None)
            if adaptive_config:
                estimated_size = getattr(adaptive_config, 'estimated_dataset_size', 100000)
                default_query_type = getattr(adaptive_config, 'default_query_type', 'concept')
                return cls.adaptive(
                    query_type=default_query_type,
                    top_k=10,  # Default, will be overridden in actual queries
                    dataset_size=estimated_size
                )
            else:
                return cls.adaptive()