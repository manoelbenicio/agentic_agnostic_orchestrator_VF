import asyncio
from typing import Any

class AdapterTestHarness:
    """
    A standardized test harness for validating that any BaseAdapter implementation 
    correctly adheres to the required contract and behaviors.
    """
    
    def __init__(self, adapter: Any, valid_model: str, invalid_model: str = "invalid-model-xyz123"):
        self.adapter = adapter
        self.valid_model = valid_model
        self.invalid_model = invalid_model

    async def test_health_check(self):
        """Validates the health check endpoint responds successfully."""
        result = await self.adapter.health_check()
        assert result is not False, "Health check failed or returned False."

    async def test_list_models_returns_list(self):
        """Validates that the adapter correctly lists available models."""
        models = await self.adapter.list_models()
        assert isinstance(models, list), "list_models must return a list."
        assert len(models) > 0, "list_models should not be empty."

    async def test_complete_returns_result(self):
        """Validates that a standard completion request returns a valid response."""
        messages = [{"role": "user", "content": "Say hello."}]
        result = await self.adapter.complete(model=self.valid_model, messages=messages)
        assert result is not None, "Complete returned None, expected a response object."

    async def test_stream_yields_chunks(self):
        """Validates that streaming completions yield chunk iterators."""
        messages = [{"role": "user", "content": "Count from 1 to 5 slowly."}]
        stream = await self.adapter.stream(model=self.valid_model, messages=messages)
        
        chunks = []
        async for chunk in stream:
            chunks.append(chunk)
            
        assert len(chunks) > 0, "Stream should yield at least one chunk."

    async def test_invalid_model_raises(self):
        """Validates that requesting a non-existent model properly raises an exception."""
        messages = [{"role": "user", "content": "Hello"}]
        raised = False
        try:
            await self.adapter.complete(model=self.invalid_model, messages=messages)
        except Exception:
            raised = True
            
        assert raised, "Adapter should have raised an exception for an invalid model."

    async def test_cost_estimation_positive(self):
        """Validates that cost estimation returns a numeric value >= 0."""
        messages = [{"role": "user", "content": "Hello"}]
        cost = await self.adapter.estimate_cost(model=self.valid_model, messages=messages)
        assert isinstance(cost, (int, float)), "Estimated cost must be numeric."
        assert cost >= 0, "Estimated cost cannot be negative."

    async def test_concurrent_requests(self, n: int = 10):
        """
        Validates the adapter handles concurrent requests safely without blocking 
        or failing (useful for catching race conditions or connection pooling limits).
        """
        messages = [{"role": "user", "content": "Hello"}]
        
        async def run_single():
            return await self.adapter.complete(model=self.valid_model, messages=messages)
            
        tasks = [run_single() for _ in range(n)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for idx, res in enumerate(results):
            assert not isinstance(res, Exception), f"Concurrent request {idx} failed: {res}"

    async def run_all(self):
        """Execute the entire suite of checks sequentially."""
        await self.test_health_check()
        await self.test_list_models_returns_list()
        await self.test_complete_returns_result()
        await self.test_stream_yields_chunks()
        await self.test_invalid_model_raises()
        await self.test_cost_estimation_positive()
        await self.test_concurrent_requests(n=10)
