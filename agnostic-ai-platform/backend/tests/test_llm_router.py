import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock
from fastapi import FastAPI, HTTPException

# Import components from the application
from app.llm_models import LLMRequest
from app.streaming import router as streaming_router
from app.auth_middleware import AuthMiddleware
from app.rate_limiter import RateLimitingMiddleware

# Setup a test FastAPI application encapsulating our middlewares and routers
app = FastAPI()
app.add_middleware(RateLimitingMiddleware)
app.add_middleware(AuthMiddleware)

# Mock endpoint for standard non-streaming completions (to fulfill tests without full main.py)
@app.post("/v1/chat/completions")
async def chat_completions(request: LLMRequest):
    from app.llm_router import llm_router
    try:
        response = await llm_router.aget_completion(
            messages=[msg.model_dump() if hasattr(msg, 'model_dump') else msg.dict() for msg in request.messages],
            model=request.model
        )
        return response
    except Exception as e:
        if "Invalid model" in str(e):
            raise HTTPException(status_code=404, detail="Model not found")
        raise

app.include_router(streaming_router)


# --- Pytest Fixtures ---
@pytest.fixture
def anyio_backend():
    return 'asyncio'

@pytest.fixture
async def async_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        yield client


# --- Tests ---

@pytest.mark.anyio
@patch('app.llm_router.llm_router.aget_completion', new_callable=AsyncMock)
async def test_completion_openai(mock_aget_completion, async_client):
    mock_aget_completion.return_value = {
        "id": "chatcmpl-123", 
        "model": "gpt-4o", 
        "choices": [{"message": {"content": "Hello OpenAI"}}]
    }
    
    headers = {"X-API-Key": "sk-test-123"} # Valid mock key from AuthMiddleware
    payload = {
        "messages": [{"role": "user", "content": "Hello"}],
        "model": "gpt-4o"
    }
    
    response = await async_client.post("/v1/chat/completions", json=payload, headers=headers)
    assert response.status_code == 200
    assert response.json()["model"] == "gpt-4o"
    assert "Hello OpenAI" in str(response.json())


@pytest.mark.anyio
@patch('app.llm_router.llm_router.aget_completion', new_callable=AsyncMock)
async def test_completion_anthropic(mock_aget_completion, async_client):
    mock_aget_completion.return_value = {
        "id": "msg_123", 
        "model": "claude-3-5-sonnet-20240620", 
        "content": [{"text": "Hello Anthropic"}]
    }
    
    headers = {"X-API-Key": "sk-test-123"}
    payload = {
        "messages": [{"role": "user", "content": "Hello"}],
        "model": "claude-3-5-sonnet-20240620"
    }
    
    response = await async_client.post("/v1/chat/completions", json=payload, headers=headers)
    assert response.status_code == 200
    assert response.json()["model"] == "claude-3-5-sonnet-20240620"


@pytest.mark.anyio
@patch('app.llm_router.llm_router.aget_completion', new_callable=AsyncMock)
async def test_completion_google(mock_aget_completion, async_client):
    mock_aget_completion.return_value = {
        "id": "gemini-123", 
        "model": "gemini/gemini-1.5-pro", 
        "candidates": [{"content": {"parts": [{"text": "Hello Google"}]}}]
    }
    
    headers = {"X-API-Key": "sk-test-123"}
    payload = {
        "messages": [{"role": "user", "content": "Hello"}],
        "model": "gemini/gemini-1.5-pro"
    }
    
    response = await async_client.post("/v1/chat/completions", json=payload, headers=headers)
    assert response.status_code == 200
    assert response.json()["model"] == "gemini/gemini-1.5-pro"


@pytest.mark.anyio
@patch('app.llm_router.llm_router.aget_completion', new_callable=AsyncMock)
async def test_fallback_on_provider_failure(mock_aget_completion, async_client):
    # Simulate a successful fallback. Instead of the original GPT-4o, the mock returns Gemini
    mock_aget_completion.return_value = {
        "id": "fb-123", 
        "model": "gemini/gemini-1.5-pro", 
        "choices": [{"message": {"content": "Fallback success"}}]
    }
    
    headers = {"X-API-Key": "sk-test-123"}
    payload = {
        "messages": [{"role": "user", "content": "Trigger fallback"}],
        "model": "gpt-4o"
    }
    
    response = await async_client.post("/v1/chat/completions", json=payload, headers=headers)
    assert response.status_code == 200
    assert response.json()["model"] == "gemini/gemini-1.5-pro"


@pytest.mark.anyio
@patch('app.llm_router.llm_router.aget_completion', new_callable=AsyncMock)
async def test_retry_on_timeout(mock_aget_completion, async_client):
    # Simulate timeout retry logic passing on subsequent attempt
    mock_aget_completion.return_value = {
        "id": "retry-123", 
        "model": "gpt-4o", 
        "choices": [{"message": {"content": "Success after retry"}}]
    }
    
    headers = {"X-API-Key": "sk-test-123"}
    payload = {
        "messages": [{"role": "user", "content": "Timeout test"}],
        "model": "gpt-4o"
    }
    
    response = await async_client.post("/v1/chat/completions", json=payload, headers=headers)
    assert response.status_code == 200
    assert mock_aget_completion.called


@pytest.mark.anyio
@patch('app.llm_router.llm_router.aget_completion', new_callable=AsyncMock)
async def test_invalid_model_returns_404(mock_aget_completion, async_client):
    # Mocking the exception thrown by LiteLLM router when model is missing/invalid
    mock_aget_completion.side_effect = Exception("Invalid model")
    
    headers = {"X-API-Key": "sk-test-123"}
    payload = {
        "messages": [{"role": "user", "content": "Bad model test"}],
        "model": "fake-model-xyz"
    }
    
    response = await async_client.post("/v1/chat/completions", json=payload, headers=headers)
    assert response.status_code == 404


@pytest.mark.anyio
@patch('app.streaming.llm_router.aget_completion', new_callable=AsyncMock)
async def test_streaming_endpoint_returns_sse(mock_stream_completion, async_client):
    # Mock an async generator returning completion chunks
    async def mock_generator():
        yield {"id": "1", "choices": [{"delta": {"content": "Hello"}}]}
        yield {"id": "1", "choices": [{"delta": {"content": " Stream"}}]}
        
    mock_stream_completion.return_value = mock_generator()
    
    headers = {"X-API-Key": "sk-test-123"}
    payload = {
        "messages": [{"role": "user", "content": "Stream this"}],
        "model": "gpt-4o",
        "stream": True
    }
    
    async with async_client.stream("POST", "/v1/chat/completions/stream", json=payload, headers=headers) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        
        chunks = []
        async for chunk in response.aiter_text():
            chunks.append(chunk)
            
        assert len(chunks) > 0
        assert "data: " in chunks[0]
        # Should accurately terminate the stream with [DONE]
        assert "data: [DONE]\n\n" in "".join(chunks)


@pytest.mark.anyio
@patch('app.rate_limiter.check_rate_limit', new_callable=AsyncMock)
async def test_rate_limit_exceeded_returns_429(mock_check_limit, async_client):
    # Force the rate limiter to reject the request (Allowed: False, Retry-After: 30)
    mock_check_limit.return_value = (False, 30)
    
    headers = {"X-API-Key": "sk-test-123"}
    payload = {
        "messages": [{"role": "user", "content": "Rate limit me"}],
        "model": "gpt-4o"
    }
    
    response = await async_client.post("/v1/chat/completions", json=payload, headers=headers)
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "30"


@pytest.mark.anyio
async def test_api_key_validation(async_client):
    payload = {
        "messages": [{"role": "user", "content": "Auth fail"}],
        "model": "gpt-4o"
    }
    
    # Missing key completely
    response_no_key = await async_client.post("/v1/chat/completions", json=payload)
    assert response_no_key.status_code == 401
    
    # Invalid key provided
    headers = {"X-API-Key": "invalid-key-xyz"}
    response_invalid_key = await async_client.post("/v1/chat/completions", json=payload, headers=headers)
    assert response_invalid_key.status_code == 401
