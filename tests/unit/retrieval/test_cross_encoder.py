"""Unit tests for cross-encoder reranking."""

import unittest
from unittest.mock import MagicMock, patch

from kb.retrieval.cross_encoder_rerank import CrossEncoderReranker


class TestCrossEncoderReranker(unittest.TestCase):
    def test_initialization_with_mock_model(self):
        """Test initialization with test-model (no external dependency needed)."""
        # Even if sentence-transformers is NOT available, test-model should work
        with patch("kb.retrieval.cross_encoder_rerank._SENTENCE_TRANSFORMERS_AVAILABLE", False):
            reranker = CrossEncoderReranker(model_name="test-model")
            self.assertTrue(reranker.enabled)
            self.assertIsNotNone(reranker.model)

            # Verify mock model behavior
            scores = reranker.model.predict([["q", "d"]])
            self.assertEqual(scores, [0.5])

    def test_rerank_basic(self):
        """Test basic reranking functionality."""
        reranker = CrossEncoderReranker(model_name="test-model")

        # Mock the predict method to return specific scores
        reranker.model.predict = MagicMock(return_value=[0.9, 0.1, 0.5])

        results = [
            {"id": 1, "text": "doc1"},
            {"id": 2, "text": "doc2"},
            {"id": 3, "text": "doc3"},
        ]

        reranked = reranker.rerank("query", results)

        # Should be sorted by score descending: 0.9 (doc1), 0.5 (doc3), 0.1 (doc2)
        self.assertEqual(len(reranked), 3)
        self.assertEqual(reranked[0]["id"], 1)
        self.assertEqual(reranked[0]["rerank_score"], 0.9)
        self.assertEqual(reranked[1]["id"], 3)
        self.assertEqual(reranked[1]["rerank_score"], 0.5)
        self.assertEqual(reranked[2]["id"], 2)
        self.assertEqual(reranked[2]["rerank_score"], 0.1)

    def test_rerank_threshold(self):
        """Test filtering by score threshold."""
        reranker = CrossEncoderReranker(model_name="test-model")
        reranker.model.predict = MagicMock(return_value=[0.9, 0.1, 0.5])

        results = [
            {"id": 1, "text": "doc1"},
            {"id": 2, "text": "doc2"},
            {"id": 3, "text": "doc3"},
        ]

        # Threshold 0.6 should only keep doc1 (0.9)
        reranked = reranker.rerank("query", results, score_threshold=0.6)

        self.assertEqual(len(reranked), 1)
        self.assertEqual(reranked[0]["id"], 1)

    def test_rerank_empty(self):
        """Test reranking with empty results."""
        reranker = CrossEncoderReranker(model_name="test-model")
        reranked = reranker.rerank("query", [])
        self.assertEqual(reranked, [])

    @patch("kb.retrieval.cross_encoder_rerank._SENTENCE_TRANSFORMERS_AVAILABLE", False)
    def test_dependencies_missing(self):
        """Test behavior when dependencies are missing."""
        # Force reload to pick up patched constant if needed, but here we just patch the class checking it
        # The class checks the constant in __init__

        # Since _SENTENCE_TRANSFORMERS_AVAILABLE is checked in __init__, we patch it there
        with patch("kb.retrieval.cross_encoder_rerank._SENTENCE_TRANSFORMERS_AVAILABLE", False):
            reranker = CrossEncoderReranker(model_name="real-model")
            self.assertFalse(reranker.enabled)
            self.assertIsNone(reranker.model)

            # Rerank should return original results
            results = [{"id": 1}]
            reranked = reranker.rerank("query", results)
            self.assertEqual(reranked, results)

    @patch("kb.retrieval.cross_encoder_rerank._SENTENCE_TRANSFORMERS_AVAILABLE", True)
    @patch("kb.retrieval.cross_encoder_rerank._CrossEncoder")
    def test_real_model_loading(self, mock_cls):
        """Test loading a 'real' model when dependencies are present."""
        reranker = CrossEncoderReranker(model_name="real-model")

        self.assertTrue(reranker.enabled)
        mock_cls.assert_called_with("real-model")

    @patch("kb.retrieval.cross_encoder_rerank._SENTENCE_TRANSFORMERS_AVAILABLE", True)
    @patch("kb.retrieval.cross_encoder_rerank._CrossEncoder")
    def test_real_model_loading_with_device(self, mock_cls):
        """Test loading a 'real' model with device argument."""
        reranker = CrossEncoderReranker(model_name="real-model", device="cpu")

        self.assertTrue(reranker.enabled)
        mock_cls.assert_called_with("real-model", device="cpu")
