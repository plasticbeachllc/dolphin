"""Cross-encoder reranking for search results."""

from __future__ import annotations

import logging
import os
import tempfile
from collections.abc import Sequence
from contextlib import contextmanager

import numpy as np

_log = logging.getLogger(__name__)

# Try to import sentence_transformers at module level for easier mocking
try:
    from sentence_transformers import CrossEncoder as _CrossEncoder

    _SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    _CrossEncoder: type | None = None
    _SENTENCE_TRANSFORMERS_AVAILABLE = False


@contextmanager
def _quiet_model_load():
    """Suppress noisy stdout/stderr and library logs during model loading.

    Redirects stdout to ``/dev/null`` and stderr to a temporary buffer so that
    native extension output (safetensors, torch, etc.) is captured.  On success
    the buffer is discarded; on exception the captured stderr is replayed so
    native-layer diagnostics (CUDA errors, OOM, etc.) are not lost.

    **Threading constraint**: fd redirection is process-global.  This must only
    be called during synchronous startup (``__init__``) before the server
    accepts connections.  Any threads writing to fd 1/2 concurrently will have
    output captured or discarded.  httpx/httpcore are handled at the server
    level (``server.py``) and intentionally excluded here so that non-server
    callers keep their own log levels after the context exits.
    """
    # Suppress noisy loggers from the ML stack (httpx/httpcore handled by server.py).
    # Wrapped in an outer try/finally so levels are restored even if fd setup fails.
    noisy_loggers = ["transformers", "sentence_transformers", "huggingface_hub"]
    prev_levels = {}
    for name in noisy_loggers:
        lgr = logging.getLogger(name)
        prev_levels[name] = lgr.level
        lgr.setLevel(logging.WARNING)

    try:
        # Capture stderr to a temp file for replay on failure; stdout goes to /dev/null.
        # Guard each allocation so partial failures don't leak fds.
        stderr_capture = tempfile.TemporaryFile()
        devnull_fd = saved_stdout = saved_stderr = -1
        try:
            devnull_fd = os.open(os.devnull, os.O_WRONLY)
            saved_stdout = os.dup(1)
            saved_stderr = os.dup(2)
        except OSError:
            for fd in (devnull_fd, saved_stdout, saved_stderr):
                if fd >= 0:
                    os.close(fd)
            stderr_capture.close()
            raise

        # dup2 calls mutate process-global fd state — keep them inside try so
        # finally always restores even if the second dup2 fails.
        failed = False
        try:
            os.dup2(devnull_fd, 1)
            os.dup2(stderr_capture.fileno(), 2)
            yield
        except BaseException:
            failed = True
            raise
        finally:
            os.close(devnull_fd)  # close our copy; fd 1 now independently references /dev/null
            os.dup2(saved_stdout, 1)
            os.close(saved_stdout)
            os.dup2(saved_stderr, 2)
            os.close(saved_stderr)
            try:
                if failed:
                    stderr_capture.seek(0)
                    captured = stderr_capture.read()
                    if captured:
                        os.write(2, captured)
            finally:
                stderr_capture.close()
    finally:
        for name in noisy_loggers:
            logging.getLogger(name).setLevel(prev_levels[name])


class CrossEncoderReranker:
    """Rerank search results using a cross-encoder model."""

    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        device: str | None = None,
        batch_size: int = 32,
    ):
        self.model_name = model_name
        self.batch_size = batch_size
        self.enabled = False
        self.model = None
        self.load_error: str | None = None  # Set when model loading fails

        if model_name == "test-model":
            self.model = self._create_mock_model()
            self.enabled = True
            _log.info("Cross-encoder running in test mode.")
            return

        if not _SENTENCE_TRANSFORMERS_AVAILABLE:
            self.load_error = "dependencies missing — install with: uv pip install pb-dolphin[reranking]"
            _log.error(
                "⚠️  Cross-encoder reranking is enabled in config but dependencies are missing!\n"
                "   Required: torch and sentence-transformers (~2GB install)\n"
                "   Install with: pip install pb-dolphin[reranking]\n"
                "   Or with uv: uv pip install pb-dolphin[reranking]\n"
                "   Reranking will be disabled until dependencies are installed."
            )
            return

        try:
            _log.info(f"Loading cross-encoder model: {model_name}")
            # Only pass device parameter if explicitly set (avoid empty string error)
            # Type narrowing: _CrossEncoder is available when _SENTENCE_TRANSFORMERS_AVAILABLE is True
            if _CrossEncoder is None:
                raise RuntimeError("CrossEncoder is not available")
            with _quiet_model_load():
                if device:
                    self.model = _CrossEncoder(model_name, device=device)
                else:
                    self.model = _CrossEncoder(model_name)
            self.enabled = True
            _log.info(f"Cross-encoder loaded successfully on {self.model.device}")
        except Exception as e:
            self.load_error = str(e)
            _log.error("Failed to load cross-encoder model: %s. Reranking disabled.", e, exc_info=True)

    def _create_mock_model(self):
        """Creates a mock model object for testing."""

        class MockModel:
            device = "cpu"

            def predict(self, *args, **kwargs):
                num_pairs = len(args[0]) if args else 0
                return [0.5] * num_pairs

        return MockModel()

    def rerank(
        self,
        query: str,
        results: Sequence[dict],
        top_k: int = 5,
        text_field: str = "text",
        score_threshold: float | None = None,
    ) -> list[dict]:
        """Reranks results using the cross-encoder model."""
        if not self.enabled or not self.model:
            _log.warning("Cross-encoder is not available or enabled. Returning original order.")
            return list(results[:top_k])

        if not results:
            return []

        pairs = [[query, r.get(text_field, "")] for r in results]

        try:
            scores = self.model.predict(pairs, batch_size=self.batch_size, show_progress_bar=False)

            if isinstance(scores, np.ndarray):
                scores = scores.tolist()

            for result, score in zip(results, scores):
                result["rerank_score"] = float(score)

            # Filter and sort
            reranked_results = [r for r in results if score_threshold is None or r["rerank_score"] >= score_threshold]
            reranked_results.sort(key=lambda x: x["rerank_score"], reverse=True)

            return reranked_results[:top_k]

        except Exception as e:
            _log.error(f"Reranking failed: {e}. Returning original results.")
            return list(results[:top_k])
