import pytest
from unittest.mock import patch, MagicMock
from httpx import Response
from ai_runtime.glm_client import GlmGenerationClient
from ai_runtime.models import ChatMessage, GenerationRequest, MessageRole


@patch("httpx.Client.post")
def test_glm_client_complete(mock_post):
    """Test that GlmGenerationClient correctly formats requests and parses responses."""
    client = GlmGenerationClient(api_key="test-api-key")
    
    request = GenerationRequest(
        model="glm-4",
        messages=(
            ChatMessage(role=MessageRole.USER, content="Hello GLM!"),
        ),
        context_window_tokens=1000,
        max_output_tokens=100,
        temperature=0.5,
        stop=("STOP",),
    )

    # Mock the HTTP POST request to Zhipu AI
    mock_response = MagicMock(spec=Response)
    mock_response.json.return_value = {
        "model": "glm-4",
        "choices": [
            {
                "message": {"role": "assistant", "content": "Hello! I am GLM."},
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30
        }
    }
    mock_post.return_value = mock_response

    response = client.complete(request)

    assert mock_post.called
    assert response.model == "glm-4"
    assert response.content == "Hello! I am GLM."
    assert response.prompt_tokens == 10
    assert response.completion_tokens == 20
    assert response.total_tokens == 30
    assert response.finish_reason == "stop"
    
    # Check the request payload
    called_url, = mock_post.call_args.args
    called_kwargs = mock_post.call_args.kwargs
    assert called_url == "https://open.bigmodel.cn/api/paas/v4/chat/completions"
    assert called_kwargs["headers"]["Authorization"] == "Bearer test-api-key"
    assert called_kwargs["json"]["model"] == "glm-4"
    assert called_kwargs["json"]["messages"][0]["content"] == "Hello GLM!"
