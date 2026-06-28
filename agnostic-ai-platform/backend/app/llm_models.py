from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class Message(BaseModel):
    role: str = Field(..., description="The role of the message author (e.g., 'user', 'assistant', 'system')")
    content: str = Field(..., description="The content of the message")

class LLMRequest(BaseModel):
    messages: List[Message] = Field(..., description="The sequence of messages for the conversation")
    model: str = Field(default="gpt-4o", description="The primary model to use for the request")
    temperature: Optional[float] = Field(default=0.7, description="Sampling temperature")
    max_tokens: Optional[int] = Field(default=None, description="Maximum number of tokens to generate")
    stream: Optional[bool] = Field(default=False, description="Whether to stream the response")
    top_p: Optional[float] = Field(default=1.0, description="Nucleus sampling threshold")
    
class LLMUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

class LLMResponse(BaseModel):
    id: str = Field(..., description="Unique identifier for the response")
    model: str = Field(..., description="The model that actually generated the response (could be a fallback)")
    content: str = Field(..., description="The generated text content")
    usage: Optional[LLMUsage] = Field(default=None, description="Token usage details")
    finish_reason: Optional[str] = Field(default=None, description="Reason the generation finished (e.g., 'stop', 'length')")
