import json
import logging
from typing import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from .llm_router import llm_router
from .llm_models import LLMRequest

logger = logging.getLogger(__name__)

router = APIRouter()

async def generate_sse_events(request: LLMRequest) -> AsyncGenerator[str, None]:
    """
    Async generator that yields SSE events from LiteLLM streaming completion.
    Implements token-by-token yield with proper SSE format and mid-stream error handling.
    """
    try:
        # Convert Pydantic messages to dicts for LiteLLM
        messages_dict = [msg.model_dump() if hasattr(msg, "model_dump") else msg.dict() for msg in request.messages]
        
        # Extract additional generation parameters
        kwargs = request.model_dump(exclude={"messages", "model", "stream"}, exclude_unset=True)
        
        # Get the streaming response wrapper from our LiteLLM router
        response_stream = await llm_router.aget_completion(
            model=request.model,
            messages=messages_dict,
            stream=True,
            **kwargs
        )
        
        # Iterate over the token chunks
        async for chunk in response_stream:
            # Safely serialize the chunk object to dict
            if hasattr(chunk, 'model_dump'):
                chunk_dict = chunk.model_dump()
            elif hasattr(chunk, 'dict'):
                chunk_dict = chunk.dict()
            else:
                try:
                    chunk_dict = dict(chunk)
                except Exception:
                    chunk_dict = str(chunk)
            
            # Yield token-by-token with proper SSE format (data: {json}\n\n)
            yield f"data: {json.dumps(chunk_dict)}\n\n"
            
        # Yield the standardized termination signal
        yield "data: [DONE]\n\n"
        
    except Exception as e:
        logger.error(f"Error during mid-stream generation: {str(e)}")
        # Output an error SSE event so the client knows the stream failed
        error_payload = {"error": {"message": str(e), "type": "stream_error"}}
        yield f"data: {json.dumps(error_payload)}\n\n"


@router.post("/v1/chat/completions/stream")
async def chat_completions_stream(request: LLMRequest):
    """
    FastAPI endpoint for streaming LLM responses via Server-Sent Events (SSE).
    """
    # Enforce the stream flag on the request for safety
    request.stream = True
    
    # Return the FastAPI StreamingResponse wrapper
    return StreamingResponse(
        generate_sse_events(request),
        media_type="text/event-stream"
    )
