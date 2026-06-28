import logging
from typing import Any
import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/llm", tags=["LLM Gateway"])
logger = logging.getLogger(__name__)

# Providers in order of fallback priority
PROVIDERS = [
    {"name": "openai", "url": "http://mock-openai:8080/v1/chat/completions"},
    {"name": "anthropic", "url": "http://mock-anthropic:8080/v1/messages"},
    {"name": "gemini", "url": "http://mock-gemini:8080/v1/chat/completions"},
]

@router.post("/chat/completions")
async def chat_completions(request: Request) -> Any:
    """
    LLM Gateway endpoint that routes chat completions.
    Implements a fallback mechanism for 429 and 5xx errors.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    # Forward relevant headers to the provider
    headers = dict(request.headers)
    # Remove headers that could cause issues with the proxy request
    headers.pop("host", None)
    headers.pop("content-length", None)

    last_error_status = 503
    last_error_text = "No providers available"

    async with httpx.AsyncClient() as client:
        for provider in PROVIDERS:
            logger.info(f"Routing request to provider: {provider['name']}")
            try:
                # Dispatch the request to the current provider
                response = await client.post(
                    provider["url"],
                    json=body,
                    headers=headers,
                    timeout=30.0
                )
                
                # If we get a Rate Limit (429) or Server Error (5xx), fallback to next provider
                if response.status_code in (429, 500, 502, 503, 504):
                    logger.warning(
                        f"Provider {provider['name']} failed with status {response.status_code}. "
                        "Falling back to next provider..."
                    )
                    last_error_status = response.status_code
                    last_error_text = response.text
                    continue
                
                # If successful or a client error (e.g., 400 Bad Request), return immediately
                # Try to return JSON if possible, otherwise text
                try:
                    return response.json()
                except Exception:
                    return response.text
                
            except httpx.RequestError as exc:
                logger.warning(
                    f"Network error with provider {provider['name']}: {exc}. "
                    "Falling back to next provider..."
                )
                last_error_status = 502
                last_error_text = str(exc)
                continue

    # If all providers fail, raise the last encountered error
    raise HTTPException(
        status_code=last_error_status, 
        detail=f"All fallback providers exhausted. Last error: {last_error_text}"
    )

@router.post("/chat/stream")
async def chat_stream(request: Request) -> StreamingResponse:
    """
    LLM Gateway endpoint that routes chat completions with SSE streaming.
    Implements a fallback mechanism for 429 and 5xx errors.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    headers = dict(request.headers)
    headers.pop("host", None)
    headers.pop("content-length", None)
    
    # Ensure stream is True for the upstream provider
    body["stream"] = True

    async def event_generator():
        last_error_status = 503
        last_error_text = "No providers available"

        async with httpx.AsyncClient() as client:
            for provider in PROVIDERS:
                logger.info(f"Routing streaming request to provider: {provider['name']}")
                try:
                    async with client.stream(
                        "POST", 
                        provider["url"], 
                        json=body, 
                        headers=headers, 
                        timeout=30.0
                    ) as response:
                        if response.status_code in (429, 500, 502, 503, 504):
                            logger.warning(
                                f"Provider {provider['name']} failed with status {response.status_code}. "
                                "Falling back to next provider..."
                            )
                            last_error_status = response.status_code
                            await response.aread()
                            last_error_text = response.text
                            continue
                            
                        # If successful, yield chunks
                        async for chunk in response.aiter_bytes():
                            yield chunk
                        
                        return
                        
                except httpx.RequestError as exc:
                    logger.warning(
                        f"Network error with provider {provider['name']}: {exc}. "
                        "Falling back to next provider..."
                    )
                    last_error_status = 502
                    last_error_text = str(exc)
                    continue

        import json
        error_msg = json.dumps({"error": f"All fallback providers exhausted. Last error: {last_error_text}"})
        yield f"data: {error_msg}\\n\\n".encode("utf-8")
        yield b"data: [DONE]\\n\\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
