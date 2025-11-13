"""Unit tests for the CrossEncoderReranker."""

from unittest.mock import MagicMock, Mock, patch

import pytest

from kb.retrieval.cross_encoder_rerank import CrossEncoderReranker


class TestCrossEncoderReranker:
    """Test cases for the CrossEncoderReranker."""

    @patch("kb.retrieval.cross_encoder_rerank._SENTENCE_TRANSFORMERS_AVAILABLE", True)
    @patch("kb.retrieval.cross_encoder_rerank._CrossEncoder")
    def test_initialization_success(self, mock_cross_encoder):
        """Test successful initialization of the reranker."""
        mock_model = MagicMock()
        mock_model.device = "cpu"
        mock_cross_encoder.return_value = mock_model

        reranker = CrossEncoderReranker()
        assert reranker.enabled
        mock_cross_encoder.assert_called_once()

    @patch("kb.retrieval.cross_encoder_rerank._SENTENCE_TRANSFORMERS_AVAILABLE", False)
    def test_initialization_import_error(self):
        """Test initialization failure due to ImportError."""
        reranker = CrossEncoderReranker()
        assert not reranker.enabled

    def test_rerank_empty_results(self):
        """Test reranking with an empty list of results."""
        reranker = CrossEncoderReranker()
        reranker.enabled = True  # Assume model is loaded
        results = reranker.rerank("query", [])
        assert results == []

    @patch("kb.retrieval.cross_encoder_rerank._SENTENCE_TRANSFORMERS_AVAILABLE", True)
    @patch("kb.retrieval.cross_encoder_rerank._CrossEncoder")
    def test_rerank_logic(self, mock_cross_encoder):
        """Test the core reranking logic."""
        mock_model = MagicMock()
        mock_model.device = "cpu"
        mock_model.predict.return_value = [0.9, 0.1, 0.5]
        mock_cross_encoder.return_value = mock_model

        reranker = CrossEncoderReranker()

        results = [
            {"text": "result 1", "score": 0.8},
            {"text": "result 2", "score": 0.7},
            {"text": "result 3", "score": 0.6},
        ]

        reranked = reranker.rerank("query", results, top_k=2)

        assert len(reranked) == 2
        assert reranked[0]["rerank_score"] == 0.9
        assert reranked[1]["rerank_score"] == 0.5
        mock_model.predict.assert_called_once()

    @patch("kb.retrieval.cross_encoder_rerank._SENTENCE_TRANSFORMERS_AVAILABLE", True)
    @patch("kb.retrieval.cross_encoder_rerank._CrossEncoder")
    def test_rerank_with_score_threshold(self, mock_cross_encoder):
        """Test reranking with a score threshold."""
        mock_model = MagicMock()
        mock_model.device = "cpu"
        mock_model.predict.return_value = [0.9, 0.4, 0.7]
        mock_cross_encoder.return_value = mock_model

        reranker = CrossEncoderReranker()

        results = [
            {"text": "result 1"},
            {"text": "result 2"},
            {"text": "result 3"},
        ]

        reranked = reranker.rerank("query", results, score_threshold=0.5)

        assert len(reranked) == 2
        assert all(r["rerank_score"] >= 0.5 for r in reranked)

    @patch("kb.retrieval.cross_encoder_rerank._SENTENCE_TRANSFORMERS_AVAILABLE", True)
    @patch("kb.retrieval.cross_encoder_rerank._CrossEncoder")
    def test_rerank_disabled(self, mock_cross_encoder):
        """Test that reranking returns original order when disabled."""
        mock_model = MagicMock()
        mock_model.device = "cpu"
        mock_cross_encoder.return_value = mock_model

        reranker = CrossEncoderReranker()
        reranker.enabled = False

        results = [{"text": "a"}, {"text": "b"}]
        reranked = reranker.rerank("query", results, top_k=1)

        assert reranked == [{"text": "a"}]
        mock_model.predict.assert_not_called()

    def test_initialization_test_model(self):
        """Test initialization with test model (no external dependencies)."""
        reranker = CrossEncoderReranker(model_name="test-model")
        assert reranker.enabled
        assert reranker.model is not None
        assert reranker.model.device == "cpu"
