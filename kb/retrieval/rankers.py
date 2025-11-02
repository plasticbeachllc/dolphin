"""Ranking algorithms for combining multiple search results.

This module implements various ranking fusion algorithms for combining
results from different search methods (e.g., vector search + BM25).

Mathematical Background:
- Reciprocal Rank Fusion (RRF): Combines ranked lists without requiring normalized scores
- Weighted fusion: Combines scores using learned weights
- Maximal Marginal Relevance (MMR): Balances relevance and diversity
"""

from __future__ import annotations

from typing import Sequence, Any, Callable, Optional
import math


def reciprocal_rank_fusion(
    result_lists: Sequence[Sequence[dict[str, Any]]],
    k: int = 60,
    id_field: str = "chunk_id",
    score_field: str = "score",
) -> list[dict[str, Any]]:
    """Combine multiple ranked lists using Reciprocal Rank Fusion (RRF).
    
    RRF combines ranked lists without requiring score normalization:
    RRF_score(d) = Σᵣ 1 / (k + rank_r(d))
    
    Where:
    - d: document
    - r: ranking (e.g., vector search, BM25)
    - rank_r(d): position of document d in ranking r (1-indexed)
    - k: constant to prevent high scores for top-ranked items (default: 60)
    
    Args:
        result_lists: List of result lists to combine
        k: RRF constant (higher = more conservative, default: 60)
        id_field: Field name containing unique document identifier
        score_field: Field name containing original scores
    
    Returns:
        Combined results sorted by RRF score (descending)
    
    Example:
        vector_results = [{"chunk_id": "A", "score": 0.9}, {"chunk_id": "B", "score": 0.8}]
        bm25_results = [{"chunk_id": "B", "score": 0.95}, {"chunk_id": "A", "score": 0.75}]
        
        fused = reciprocal_rank_fusion([vector_results, bm25_results])
        # Result: [{"chunk_id": "B", "rrf_score": 0.0325}, {"chunk_id": "A", "rrf_score": 0.0323}]
    """
    if not result_lists:
        return []
    
    # Collect all unique documents across all rankings
    all_documents = {}
    
    for result_list in result_lists:
        for rank, result in enumerate(result_list, 1):
            doc_id = result.get(id_field)
            if doc_id is None:
                continue
            
            if doc_id not in all_documents:
                all_documents[doc_id] = {
                    "rrf_score": 0.0,
                    id_field: doc_id,
                    "appearances": 0,
                    "rankings": [],
                }
            
            # Add to RRF score: 1 / (k + rank)
            rrf_contribution = 1.0 / (k + rank)
            all_documents[doc_id]["rrf_score"] += rrf_contribution
            all_documents[doc_id]["appearances"] += 1
            all_documents[doc_id]["rankings"].append(rank)
            
            # Keep original scores for reference
            original_score = result.get(score_field, 0.0)
            all_documents[doc_id].setdefault("original_scores", []).append(original_score)
            
            # Copy other metadata from first occurrence
            if len(all_documents[doc_id]["rankings"]) == 1:
                for key, value in result.items():
                    if key not in [id_field, score_field]:
                        all_documents[doc_id][key] = value
    
    # Sort by RRF score (descending) and return
    fused_results = sorted(
        all_documents.values(),
        key=lambda x: x["rrf_score"],
        reverse=True
    )
    
    return fused_results


def weighted_fusion(
    result_lists: Sequence[Sequence[dict[str, Any]]],
    weights: Sequence[float],
    id_field: str = "chunk_id",
    score_field: str = "score",
    normalize: bool = True,
) -> list[dict[str, Any]]:
    """Combine results using weighted score fusion.
    
    Args:
        result_lists: List of result lists to combine
        weights: Weight for each result list (must sum to 1.0)
        id_field: Field name containing unique document identifier
        score_field: Field name containing scores
        normalize: Whether to min-max normalize scores before combining
    
    Returns:
        Combined results sorted by weighted score (descending)
    """
    if len(result_lists) != len(weights):
        raise ValueError("Number of result lists must match number of weights")
    
    if abs(sum(weights) - 1.0) > 1e-6:
        raise ValueError("Weights must sum to 1.0")
    
    # Normalize scores if requested
    normalized_lists = []
    for result_list in result_lists:
        if normalize and result_list:
            scores = [r.get(score_field, 0.0) for r in result_list]
            min_score = min(scores)
            max_score = max(scores)
            
            if max_score > min_score:
                normalized = [
                    {**r, "normalized_score": (r.get(score_field, 0.0) - min_score) / (max_score - min_score)}
                    for r in result_list
                ]
            else:
                normalized = [
                    {**r, "normalized_score": 1.0}
                    for r in result_list
                ]
            normalized_lists.append(normalized)
        else:
            normalized_lists.append([
                {**r, "normalized_score": r.get(score_field, 0.0)}
                for r in result_list
            ])
    
    # Combine scores
    all_documents = {}
    
    for result_list, weight in zip(normalized_lists, weights):
        for result in result_list:
            doc_id = result.get(id_field)
            if doc_id is None:
                continue
            
            if doc_id not in all_documents:
                all_documents[doc_id] = {
                    "fused_score": 0.0,
                    id_field: doc_id,
                    "contributions": 0,
                }
            
            normalized_score = result.get("normalized_score", 0.0)
            all_documents[doc_id]["fused_score"] += weight * normalized_score
            all_documents[doc_id]["contributions"] += 1
            
            # Copy other metadata from first occurrence
            if all_documents[doc_id]["contributions"] == 1:
                for key, value in result.items():
                    if key not in [id_field, score_field, "normalized_score"]:
                        all_documents[doc_id][key] = value
    
    # Sort by fused score (descending)
    fused_results = sorted(
        all_documents.values(),
        key=lambda x: x["fused_score"],
        reverse=True
    )
    
    return fused_results


def maximal_marginal_relevance(
    query_vector: list[float],
    candidates: Sequence[dict[str, Any]],
    top_k: int = 10,
    lambda_param: float = 0.7,
    id_field: str = "chunk_id",
) -> list[dict[str, Any]]:
    """Apply Maximal Marginal Relevance (MMR) for diverse results.
    
    MMR balances relevance and diversity:
    MMR = λ * relevance - (1-λ) * similarity_to_selected
    
    Where:
    - λ: Trade-off between relevance and diversity (higher = more relevant)
    - relevance: Cosine similarity to query
    - similarity_to_selected: Max similarity to already selected documents
    
    Args:
        query_vector: Query embedding vector for relevance calculation
        candidates: Candidate documents to select from
        top_k: Number of results to return
        lambda_param: Trade-off parameter (0.7 = 70% relevance, 30% diversity)
        id_field: Field name containing unique document identifier
    
    Returns:
        Selected documents with MMR scores
    """
    if not candidates:
        return []
    
    selected = []
    candidates = list(candidates)
    
    def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        if len(vec1) != len(vec2):
            return 0.0
        
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        magnitude1 = math.sqrt(sum(a * a for a in vec1))
        magnitude2 = math.sqrt(sum(a * a for a in vec2))
        
        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0
        
        return dot_product / (magnitude1 * magnitude2)
    
    while len(selected) < top_k and candidates:
        mmr_scores = []
        
        for candidate in candidates:
            # Relevance to query
            relevance = candidate.get("score", 0.0)
            
            # Diversity penalty (similarity to selected docs)
            diversity_penalty = 0.0
            if selected:
                # Get query vector from candidate if available
                candidate_query_vector = candidate.get("query_vector", query_vector)
                
                max_similarity = max(
                    cosine_similarity(candidate_query_vector, s.get("query_vector", query_vector))
                    for s in selected
                )
                diversity_penalty = max_similarity
            
            # MMR score
            mmr_score = (lambda_param * relevance) - ((1 - lambda_param) * diversity_penalty)
            mmr_scores.append((mmr_score, candidate))
        
        # Select best MMR candidate
        best_mmr_score, best_candidate = max(mmr_scores, key=lambda x: x[0])
        
        # Find the MMR score for the selected candidate and add it
        for score, candidate in mmr_scores:
            if candidate.get(id_field) == best_candidate.get(id_field):
                best_candidate = dict(best_candidate)  # Make a copy to avoid modifying original
                best_candidate["mmr_score"] = score
                break
        
        selected.append(best_candidate)
        # Remove the original candidate (not the copy) from the list
        original_index = next(i for i, c in enumerate(candidates)
                            if c.get(id_field) == best_candidate.get(id_field))
        candidates.pop(original_index)
    
    return selected


def combine_with_confidence(
    result_lists: Sequence[Sequence[dict[str, Any]]],
    fusion_method: str = "rrf",
    id_field: str = "chunk_id",
    **fusion_kwargs,
) -> dict[str, Any]:
    """Combine results with confidence scores and metadata.
    
    Args:
        result_lists: Result lists to combine
        fusion_method: Method to use ("rrf", "weighted")
        id_field: Field containing document identifiers
        **fusion_kwargs: Additional arguments for fusion method
    
    Returns:
        Dict with combined results and metadata
    """
    # Choose fusion method
    if fusion_method == "rrf":
        fused_results = reciprocal_rank_fusion(result_lists, id_field=id_field, **fusion_kwargs)
    elif fusion_method == "weighted":
        fused_results = weighted_fusion(result_lists, id_field=id_field, **fusion_kwargs)
    else:
        raise ValueError(f"Unknown fusion method: {fusion_method}")
    
    # Calculate confidence metrics
    confidence_metrics = {
        "total_unique_docs": len(fused_results),
        "total_rankings": len(result_lists),
        "fusion_method": fusion_method,
    }
    
    # Add confidence scores based on how often documents appear
    for result in fused_results:
        appearances = result.get("appearances", 1)
        confidence = appearances / len(result_lists)
        result["confidence"] = confidence
        
        # Add source information
        result["sources"] = appearances
        result["source_methods"] = len(result_lists)
    
    return {
        "results": fused_results,
        "metadata": confidence_metrics,
    }


def create_fusion_function(
    method: str = "rrf",
    **kwargs,
) -> Callable[[Sequence[Sequence[dict[str, Any]]]], list[dict[str, Any]]]:
    """Create a fusion function with specified method and parameters.
    
    Args:
        method: Fusion method ("rrf", "weighted")
        **kwargs: Parameters for the fusion method
    
    Returns:
        Function that takes result lists and returns fused results
    """
    def rrf_fusion(result_lists: Sequence[Sequence[dict[str, Any]]]) -> list[dict[str, Any]]:
        return reciprocal_rank_fusion(result_lists, **kwargs)
    
    def weighted_fusion_wrapper(result_lists: Sequence[Sequence[dict[str, Any]]]) -> list[dict[str, Any]]:
        if "weights" not in kwargs:
            raise ValueError("Weights required for weighted fusion")
        return weighted_fusion(result_lists, **kwargs)
    
    if method == "rrf":
        return rrf_fusion
    elif method == "weighted":
        return weighted_fusion_wrapper
    else:
        raise ValueError(f"Unknown fusion method: {method}")