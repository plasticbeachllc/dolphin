"""Unit tests for DynamicWorkerPool."""

from unittest.mock import MagicMock, patch

from kb.ingest._helpers import worker_ignore_sigint
from kb.ingest.dynamic_pool import DynamicWorkerPool, WorkloadEstimator


class TestDynamicWorkerPoolInit:
    """Tests for DynamicWorkerPool initialisation."""

    def test_executor_uses_worker_ignore_sigint(self):
        """ProcessPoolExecutor must be created with worker_ignore_sigint as initializer."""
        with patch("kb.ingest.dynamic_pool.ProcessPoolExecutor") as mock_ppe:
            mock_ppe.return_value = MagicMock()
            pool = DynamicWorkerPool(max_workers=2, min_workers=1)
            pool._executor.shutdown(wait=False)

        call_kwargs = mock_ppe.call_args[1]
        assert call_kwargs.get("initializer") is worker_ignore_sigint

    def test_respects_max_workers(self):
        """Pool worker count should not exceed max_workers."""
        with patch("kb.ingest.dynamic_pool.ProcessPoolExecutor") as mock_ppe:
            mock_ppe.return_value = MagicMock()
            DynamicWorkerPool(max_workers=3, min_workers=1)

        actual_workers = mock_ppe.call_args[1]["max_workers"]
        assert actual_workers <= 3

    def test_context_manager_shuts_down(self):
        """__exit__ should call shutdown on the underlying executor."""
        with patch("kb.ingest.dynamic_pool.ProcessPoolExecutor") as mock_ppe:
            mock_executor = MagicMock()
            mock_ppe.return_value = mock_executor

            pool = DynamicWorkerPool(max_workers=2, min_workers=1)
            with pool:
                pass

        mock_executor.shutdown.assert_called_once_with(wait=True)


class TestWorkloadEstimator:
    """Tests for WorkloadEstimator.estimate_batch_size."""

    def test_zero_items_returns_min_batch(self):
        assert WorkloadEstimator.estimate_batch_size(0, 4) == 10

    def test_small_workload_clamped_to_min(self):
        result = WorkloadEstimator.estimate_batch_size(10, 2, min_batch=10, max_batch=100)
        assert result >= 10

    def test_large_workload_clamped_to_max(self):
        result = WorkloadEstimator.estimate_batch_size(100_000, 2, min_batch=10, max_batch=100)
        assert result <= 100
