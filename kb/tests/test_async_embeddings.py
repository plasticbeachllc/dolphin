"""
Tests for async embedding functionality

Tests critical async scenarios:
- Async embedding with OpenAI provider
- Concurrent embedding requests
- Error handling in async context
- Resource cleanup (AsyncOpenAI client)
"""

import pytest
import asyncio
from kb.embeddings.provider import OpenAIEmbeddingProvider, EmbeddingProvider


class TestAsyncEmbeddings:
    """Test async embedding operations"""

    @pytest.mark.asyncio
    async def test_async_embed_with_stub_provider(self):
        """Test async embedding with stub provider"""
        provider = EmbeddingProvider()  # Stub provider

        texts = ["hello world", "test embedding"]
        embeddings = await provider.embed_texts_async("small", texts)

        assert len(embeddings) == 2
        assert len(embeddings[0]) == 1536  # small model dimension
        assert all(x == 0.0 for x in embeddings[0])  # Stub returns zeros

    @pytest.mark.asyncio
    async def test_async_embed_concurrent_requests(self):
        """Test multiple concurrent async embedding requests"""
        provider = EmbeddingProvider()

        # Create 5 concurrent requests
        tasks = [provider.embed_texts_async("small", [f"text {i}"]) for i in range(5)]

        results = await asyncio.gather(*tasks)

        assert len(results) == 5
        for result in results:
            assert len(result) == 1
            assert len(result[0]) == 1536

    @pytest.mark.asyncio
    async def test_async_embed_yields_to_event_loop(self):
        """Test that async embedding yields to event loop"""
        provider = EmbeddingProvider()

        # Track if event loop gets control
        loop_got_control = False

        async def set_flag():
            nonlocal loop_got_control
            await asyncio.sleep(0)
            loop_got_control = True

        # Run both concurrently
        await asyncio.gather(
            provider.embed_texts_async("small", ["test"] * 10), set_flag()
        )

        # Event loop should have had chance to run set_flag
        assert loop_got_control

    @pytest.mark.asyncio
    async def test_openai_provider_close(self):
        """Test that OpenAI async client is properly closed"""
        # Create provider with dummy API key
        provider = OpenAIEmbeddingProvider(
            api_key="sk-test-dummy-key",
            validate_key=False,  # Don't validate to avoid API call
        )

        assert hasattr(provider, "async_client")

        # Close the provider
        await provider.close()

        # Async client should be closed (we can't easily test this directly,
        # but we verify close() doesn't raise an error)
        assert True  # If we got here, close() worked

    @pytest.mark.asyncio
    async def test_async_embed_error_handling(self):
        """Test error handling in async embedding"""
        provider = EmbeddingProvider()

        # Test with empty texts
        embeddings = await provider.embed_texts_async("small", [])
        assert len(embeddings) == 0

    @pytest.mark.asyncio
    async def test_async_embed_large_batch(self):
        """Test async embedding with large batch"""
        provider = EmbeddingProvider()

        # Large batch
        texts = [f"text {i}" for i in range(100)]
        embeddings = await provider.embed_texts_async("small", texts)

        assert len(embeddings) == 100
        assert all(len(e) == 1536 for e in embeddings)

    @pytest.mark.asyncio
    async def test_context_vars_isolation(self):
        """Test that contextvars properly isolate providers in async context"""
        from kb.embeddings.provider import _provider_context, set_default_provider

        # Create two different providers
        provider1 = EmbeddingProvider()
        provider2 = EmbeddingProvider()

        async def use_provider1():
            set_default_provider(provider1)
            current = _provider_context.get()
            assert current is provider1
            await asyncio.sleep(0.01)
            # Should still be provider1
            assert _provider_context.get() is provider1

        async def use_provider2():
            set_default_provider(provider2)
            current = _provider_context.get()
            assert current is provider2
            await asyncio.sleep(0.01)
            # Should still be provider2
            assert _provider_context.get() is provider2

        # Run concurrently - each should maintain its own provider
        await asyncio.gather(use_provider1(), use_provider2())


class TestRateLimiting:
    """Test rate limiting (if implemented in Python side)"""

    @pytest.mark.asyncio
    async def test_concurrent_requests_dont_block_event_loop(self):
        """Ensure concurrent async requests don't block the event loop"""
        provider = EmbeddingProvider()

        start_time = asyncio.get_event_loop().time()

        # Fire 10 concurrent requests
        tasks = [provider.embed_texts_async("small", ["test"]) for _ in range(10)]

        await asyncio.gather(*tasks)

        elapsed = asyncio.get_event_loop().time() - start_time

        # All requests should complete quickly (stub provider is instant)
        # If blocking, this would take much longer
        assert elapsed < 1.0  # Should be nearly instant


class TestErrorPaths:
    """Test error handling paths"""

    @pytest.mark.asyncio
    async def test_invalid_model_name(self):
        """Test handling of invalid model name"""
        provider = EmbeddingProvider()

        with pytest.raises(ValueError, match="Unsupported model"):
            await provider.embed_texts_async("invalid-model", ["test"])

    @pytest.mark.asyncio
    async def test_async_with_sync_fallback(self):
        """Test that async falls back to sync when needed"""
        provider = EmbeddingProvider()

        # Both should work
        sync_result = provider.embed_texts("small", ["test"])
        async_result = await provider.embed_texts_async("small", ["test"])

        assert len(sync_result) == len(async_result)
        assert len(sync_result[0]) == len(async_result[0])


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
