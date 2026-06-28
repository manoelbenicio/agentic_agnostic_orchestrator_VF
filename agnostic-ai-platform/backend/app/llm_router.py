import logging
from typing import List, Dict, Any, Optional

import litellm
from litellm import Router, completion

# Configure basic logging
logger = logging.getLogger(__name__)

class LLMRouterWrapper:
    """
    A LiteLLM wrapper for routing requests across multiple providers 
    (OpenAI, Anthropic, Google) with model selection, fallback logic, and retries.
    """
    
    def __init__(self, use_router: bool = True, num_retries: int = 3, timeout: int = 60):
        """
        Initialize the router wrapper.
        
        Args:
            use_router (bool): If True, uses litellm.Router for load balancing and fallbacks.
            num_retries (int): Number of retries for failed requests.
            timeout (int): Timeout in seconds for requests.
        """
        self.use_router = use_router
        self.num_retries = num_retries
        self.timeout = timeout
        
        # Define fallback logic for primary models across different providers
        self.fallbacks = [
            {"gpt-4o": ["claude-3-5-sonnet-20240620", "gemini/gemini-1.5-pro"]},
            {"claude-3-5-sonnet-20240620": ["gpt-4o", "gemini/gemini-1.5-pro"]},
            {"gpt-3.5-turbo": ["claude-3-haiku-20240307", "gemini/gemini-1.5-flash"]},
            {"gemini/gemini-1.5-pro": ["gpt-4o", "claude-3-5-sonnet-20240620"]},
            {"gemini/gemini-1.5-flash": ["gpt-3.5-turbo", "claude-3-haiku-20240307"]}
        ]
        
        if self.use_router:
            # Configure model list for litellm.Router
            model_list = [
                # OpenAI Models
                {"model_name": "gpt-4o", "litellm_params": {"model": "openai/gpt-4o"}},
                {"model_name": "gpt-3.5-turbo", "litellm_params": {"model": "openai/gpt-3.5-turbo"}},
                
                # Anthropic Models
                {"model_name": "claude-3-5-sonnet-20240620", "litellm_params": {"model": "anthropic/claude-3-5-sonnet-20240620"}},
                {"model_name": "claude-3-haiku-20240307", "litellm_params": {"model": "anthropic/claude-3-haiku-20240307"}},
                
                # Google Models
                {"model_name": "gemini/gemini-1.5-pro", "litellm_params": {"model": "gemini/gemini-1.5-pro"}},
                {"model_name": "gemini/gemini-1.5-flash", "litellm_params": {"model": "gemini/gemini-1.5-flash"}}
            ]
            
            # Initialize litellm Router with retries and fallbacks
            self.router = Router(
                model_list=model_list,
                fallbacks=self.fallbacks,
                num_retries=self.num_retries,
                timeout=self.timeout
            )
            
    def get_completion(self, messages: List[Dict[str, str]], model: str = "gpt-4o", **kwargs) -> Any:
        """
        Generate a synchronous completion with model selection, retries, and fallback logic.
        """
        try:
            if self.use_router:
                # The router automatically handles fallbacks and retries
                response = self.router.completion(model=model, messages=messages, **kwargs)
            else:
                # Direct litellm completion with fallbacks and manual retry config
                model_fallbacks = next((fb.get(model, []) for fb in self.fallbacks if model in fb), [])
                        
                response = completion(
                    model=model,
                    messages=messages,
                    fallbacks=model_fallbacks,
                    num_retries=self.num_retries,
                    timeout=self.timeout,
                    **kwargs
                )
            return response
        except Exception as e:
            logger.error(f"Error generating completion for model {model}: {str(e)}")
            raise e

    async def aget_completion(self, messages: List[Dict[str, str]], model: str = "gpt-4o", **kwargs) -> Any:
        """
        Generate an asynchronous completion with model selection, retries, and fallback logic.
        """
        try:
            if self.use_router:
                response = await self.router.acompletion(model=model, messages=messages, **kwargs)
            else:
                model_fallbacks = next((fb.get(model, []) for fb in self.fallbacks if model in fb), [])
                        
                response = await litellm.acompletion(
                    model=model,
                    messages=messages,
                    fallbacks=model_fallbacks,
                    num_retries=self.num_retries,
                    timeout=self.timeout,
                    **kwargs
                )
            return response
        except Exception as e:
            logger.error(f"Error generating async completion for model {model}: {str(e)}")
            raise e

# Convenience instance
llm_router = LLMRouterWrapper(use_router=True)
