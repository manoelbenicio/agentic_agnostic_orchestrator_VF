import pytest
import asyncio
from unittest.mock import AsyncMock

# Assuming the test harness is importable as specified
from app.registry.adapters.test_harness import AdapterTestHarness

# --- Mock Adapters simulating BaseAdapter implementations ---

class MockOpenAIAdapter:
    async def health_check(self): 
        return True
    
    async def list_models(self): 
        return ["gpt-4", "gpt-4o", "gpt-3.5-turbo"]
    
    async def complete(self, model, messages):
        if model == "invalid-model-xyz123":
            raise ValueError("Model not found")
        # Simulating delay for concurrency tests
        await asyncio.sleep(0.01)
        return {"choices": [{"message": {"content": "OpenAI Response"}}]}
        
    async def stream(self, model, messages):
        async def mock_generator():
            yield "chunk 1 "
            yield "chunk 2"
        return mock_generator()
        
    async def estimate_cost(self, model, messages): 
        return 0.05


class MockAnthropicAdapter:
    async def health_check(self): 
        return True
    
    async def list_models(self): 
        return ["claude-3-opus", "claude-3-sonnet", "claude-3-haiku"]
    
    async def complete(self, model, messages):
        if model == "invalid-model-xyz123":
            raise ValueError("Model not found")
        await asyncio.sleep(0.01)
        return {"content": [{"text": "Anthropic Response"}]}
        
    async def stream(self, model, messages):
        async def mock_generator():
            yield "part 1 "
            yield "part 2"
        return mock_generator()
        
    async def estimate_cost(self, model, messages): 
        return 0.03


# --- Pytest Fixtures ---

@pytest.fixture
def anyio_backend():
    return 'asyncio'

@pytest.fixture
def openai_adapter():
    return MockOpenAIAdapter()

@pytest.fixture
def anthropic_adapter():
    return MockAnthropicAdapter()


# --- Parameterized Test Suite ---

@pytest.mark.anyio
@pytest.mark.parametrize("adapter_fixture, valid_model", [
    ("openai_adapter", "gpt-4o"),
    ("anthropic_adapter", "claude-3-opus")
])
async def test_adapter_harness_integration(adapter_fixture, valid_model, request):
    """
    Parametrized test that dynamically loads the specified adapter fixture and 
    runs it through the standardized AdapterTestHarness to ensure contract compliance.
    """
    # Dynamically fetch the adapter instance from the pytest fixture
    adapter_instance = request.getfixturevalue(adapter_fixture)
    
    # Initialize the test harness for this specific adapter
    harness = AdapterTestHarness(adapter=adapter_instance, valid_model=valid_model)
    
    # Execute all standardized tests sequentially
    await harness.test_health_check()
    await harness.test_list_models_returns_list()
    await harness.test_complete_returns_result()
    await harness.test_stream_yields_chunks()
    await harness.test_invalid_model_raises()
    await harness.test_cost_estimation_positive()
    
    # Run concurrency test (e.g. n=10 parallel requests)
    await harness.test_concurrent_requests(n=10)
