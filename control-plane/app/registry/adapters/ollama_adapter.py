import json
import logging
from typing import List, Dict, Any, AsyncGenerator
import httpx

logger = logging.getLogger("registry.adapters.ollama")

class OllamaAdapter:
    """
    Adapter for interacting with a local Ollama instance exposing the REST API.
    Implicitly conforms to the BaseAdapter integration contract.
    """
    
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url.rstrip('/')

    async def health_check(self) -> bool:
        """Verifies connection to the local Ollama instance by fetching its version."""
        url = f"{self.base_url}/api/version"
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                
                data = response.json()
                logger.debug(f"Ollama health check successful (version: {data.get('version')})")
                return True
        except Exception as e:
            logger.error(f"Ollama health check failed: {e}")
            return False

    async def list_models(self) -> List[str]:
        """Fetches the list of downloaded and available models via /api/tags."""
        url = f"{self.base_url}/api/tags"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(url)
                response.raise_for_status()
                
                data = response.json()
                models = [model.get("name") for model in data.get("models", [])]
                return models
        except Exception as e:
            logger.error(f"Failed to list Ollama models: {e}")
            # Depending on strictness, we return an empty list or raise.
            return []

    async def complete(self, model: str, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Executes a synchronous (non-streaming) completion request to the Ollama API.
        """
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": model,
            "messages": messages,
            "stream": False
        }
        
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, json=payload)
            
            # Catch invalid/un-downloaded models early to satisfy harness requirements
            if response.status_code == 404:
                raise ValueError(f"Model not found in local Ollama registry: {model}")
                
            response.raise_for_status()
            
            data = response.json()
            return data

    async def stream(self, model: str, messages: List[Dict[str, Any]]) -> AsyncGenerator[str, None]:
        """
        Executes a streaming completion request, parsing the JSONLines response format
        from Ollama and yielding text delta chunks as they arrive.
        """
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": model,
            "messages": messages,
            "stream": True
        }
        
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", url, json=payload) as response:
                if response.status_code == 404:
                    raise ValueError(f"Model not found in local Ollama registry: {model}")
                    
                response.raise_for_status()
                
                # Ollama streams back NDJSON (Newline Delimited JSON)
                async for chunk in response.aiter_lines():
                    if chunk:
                        try:
                            data = json.loads(chunk)
                            if "message" in data and "content" in data["message"]:
                                yield data["message"]["content"]
                        except json.JSONDecodeError:
                            logger.warning(f"Failed to parse Ollama NDJSON chunk: {chunk}")

    async def estimate_cost(self, model: str, messages: List[Dict[str, Any]]) -> float:
        """
        Ollama models are locally hosted and inherently free of API token charges.
        Always returns 0.0 to satisfy the interface.
        """
        return 0.0
