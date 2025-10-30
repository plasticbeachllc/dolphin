"""Ranking and fusion algorithms for search results."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Sequence


@dataclass
class RankedResult:
    """A search result with ranking information."""

    chunk_id: str
    score: float
    data: dict[str, Any]


def reciprocal_rank_fusion(
    result_lists: Sequence[Sequence[dict[str, Any]]],
    k: int = 60,
    id_field: str = "chunk_id",
) -> list[dict[str, Any]]:
    """Merge multiple ranked lists using Reciprocal Rank Fusion (RRF).

    RRF is a simple but effective method for combining ranked lists from
    different retrieval systems. It assigns each result a score based on
    its rank in each list:

        RRF_score(item) = sum(1 / (k + rank_i)) for each list where item appears

    Where:
    - k is a constant (typically 60) that balances the contribution of top-ranked items
    - rank_i is the position of the item in list i (1-indexed)

    Args:
        result_lists: List of result lists to merge. Each result list is a
                     sequence of dictionaries with at least an ID field.
        k: RRF parameter controlling rank fusion. Higher values give more
           equal weight to all ranks. Default is 60 (standard in literature).
        id_field: Name of the field containing unique result IDs. Default is 'chunk_id'.

    Returns:
        Merged and re-ranked list of results, sorted by RRF score (descending).
        Each result dict will have its 'score' field updated with the RRF score.

    Example:
        >>> list1 = [{"chunk_id": "a", "score": 0.9}, {"chunk_id": "b", "score": 0.8}]
        >>> list2 = [{"chunk_id": "b", "score": 0.95}, {"chunk_id": "c", "score": 0.7}]
        >>> merged = reciprocal_rank_fusion([list1, list2])
        >>> # Result: 'b' ranked first (appears in both), then 'a' and 'c'

    References:
        Cormack, G. V., Clarke, C. L., & Buettcher, S. (2009).
        "Reciprocal rank fusion outperforms condorcet and individual rank learning methods."
        SIGIR '09.
    """
    if not result_lists:
        return []

    # Filter out empty lists
    result_lists = [lst for lst in result_lists if lst]
    if not result_lists:
        return []

    # Compute RRF scores
    rrf_scores: dict[str, float] = defaultdict(float)
    results_by_id: dict[str, dict[str, Any]] = {}

    for result_list in result_lists:
        for rank, result in enumerate(result_list, start=1):
            result_id = result.get(id_field)
            if result_id is None:
                continue  # Skip results without ID

            # Add RRF contribution: 1 / (k + rank)
            rrf_scores[result_id] += 1.0 / (k + rank)

            # Store result data (use first occurrence if appears in multiple lists)
            if result_id not in results_by_id:
                results_by_id[result_id] = result.copy()

    # Sort by RRF score (descending) and update scores
    sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)

    merged_results = []
    for result_id in sorted_ids:
        result = results_by_id[result_id]
        # Update score with RRF score
        result["score"] = rrf_scores[result_id]
        merged_results.append(result)

    return merged_results


def weighted_score_fusion(
    result_lists: Sequence[Sequence[dict[str, Any]]],
    weights: Sequence[float] | None = None,
    id_field: str = "chunk_id",
) -> list[dict[str, Any]]:
    """Merge multiple ranked lists using weighted score combination.

    This method combines results by summing their normalized scores with
    optional weights for each result list.

        Combined_score(item) = sum(weight_i * score_i) for each list

    Args:
        result_lists: List of result lists to merge
        weights: Optional weights for each list. If None, uses equal weights.
                Must have same length as result_lists.
        id_field: Name of the field containing unique result IDs

    Returns:
        Merged list sorted by combined score (descending)

    Example:
        >>> list1 = [{"chunk_id": "a", "score": 0.9}]
        >>> list2 = [{"chunk_id": "a", "score": 0.7}]
        >>> # Give list1 twice the weight of list2
        >>> merged = weighted_score_fusion([list1, list2], weights=[2.0, 1.0])
    """
    if not result_lists:
        return []

    # Filter out empty lists and corresponding weights
    if weights is None:
        weights = [1.0] * len(result_lists)
    else:
        if len(weights) != len(result_lists):
            raise ValueError(
                f"Number of weights ({len(weights)}) must match "
                f"number of result lists ({len(result_lists)})"
            )

    # Filter empty lists
    filtered_lists_and_weights = [
        (lst, w) for lst, w in zip(result_lists, weights) if lst
    ]

    if not filtered_lists_and_weights:
        return []

    result_lists, weights = zip(*filtered_lists_and_weights)

    # Normalize weights to sum to 1
    total_weight = sum(weights)
    normalized_weights = [w / total_weight for w in weights]

    # Combine scores
    combined_scores: dict[str, float] = defaultdict(float)
    results_by_id: dict[str, dict[str, Any]] = {}

    for result_list, weight in zip(result_lists, normalized_weights):
        for result in result_list:
            result_id = result.get(id_field)
            if result_id is None:
                continue

            score = result.get("score", 0.0)
            combined_scores[result_id] += weight * score

            if result_id not in results_by_id:
                results_by_id[result_id] = result.copy()

    # Sort by combined score (descending)
    sorted_ids = sorted(
        combined_scores.keys(), key=lambda x: combined_scores[x], reverse=True
    )

    merged_results = []
    for result_id in sorted_ids:
        result = results_by_id[result_id]
        result["score"] = combined_scores[result_id]
        merged_results.append(result)

    return merged_results
