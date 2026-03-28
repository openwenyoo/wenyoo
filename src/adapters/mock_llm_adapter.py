"""
Mock LLM adapter for testing the AI Native game engine.

This module provides a mock LLM adapter that returns deterministic responses,
enabling tests to run without actual LLM API calls.
"""
from typing import Dict, List, Optional, Any
import logging
import json
import re
from src.core.interfaces import ILLMProvider

logger = logging.getLogger(__name__)


class MockLLMAdapter(ILLMProvider):
    """
    Mock LLM Adapter for testing.
    
    This adapter provides deterministic responses for testing purposes:
    - For action parsing: Returns null to use exact action ID matching
    - For text generation: Returns placeholder or scripted responses
    
    Usage:
        adapter = MockLLMAdapter()
        # Add scripted responses for specific patterns
        adapter.add_response_pattern(r".*combat.*", '{"action": "attack", "target": "enemy"}')
    """
    
    def __init__(self, model: str = "mock"):
        self.model = model
        self._response_patterns: List[tuple[str, str]] = []
        self._call_history: List[Dict[str, Any]] = []
        logger.info("MockLLMAdapter initialized for testing")
    
    def add_response_pattern(self, pattern: str, response: str) -> None:
        """
        Add a pattern-based response.
        
        When a prompt matches the pattern (regex), return the specified response.
        
        Args:
            pattern: Regex pattern to match prompts
            response: Response to return when pattern matches
        """
        self._response_patterns.append((pattern, response))
    
    def clear_patterns(self) -> None:
        """Clear all registered response patterns."""
        self._response_patterns.clear()
    
    def get_call_history(self) -> List[Dict[str, Any]]:
        """Get the history of all LLM calls made during testing."""
        return self._call_history.copy()
    
    def clear_call_history(self) -> None:
        """Clear the call history."""
        self._call_history.clear()
    
    async def generate_response(self, prompt: str, **kwargs) -> str:
        """
        Generate a mock response.
        
        Checks registered patterns first, then returns a default JSON response.
        """
        self._call_history.append({
            "method": "generate_response",
            "prompt": prompt[:200] + "..." if len(prompt) > 200 else prompt,
            "kwargs": kwargs
        })
        
        # Check for pattern matches
        for pattern, response in self._response_patterns:
            if re.search(pattern, prompt, re.IGNORECASE | re.DOTALL):
                logger.debug(f"MockLLM: Pattern matched - returning scripted response")
                return response
        
        # Default response for JSON mode
        return json.dumps({
            "mock": True,
            "message": "This is a mock LLM response for testing"
        })
    
    async def generate_text_response(self, prompt: str, system_prompt: str = None, **kwargs) -> str:
        """
        Generate a mock text response.
        
        Returns placeholder text for NPC dialogue, narratives, etc.
        """
        self._call_history.append({
            "method": "generate_text_response",
            "prompt": prompt[:200] + "..." if len(prompt) > 200 else prompt,
            "system_prompt": system_prompt[:100] + "..." if system_prompt and len(system_prompt) > 100 else system_prompt,
            "kwargs": kwargs
        })
        
        # Check for pattern matches
        for pattern, response in self._response_patterns:
            if re.search(pattern, prompt, re.IGNORECASE | re.DOTALL):
                logger.debug(f"MockLLM: Pattern matched - returning scripted response")
                return response
        
        # Default placeholder response
        return "[Mock LLM Response - Testing Mode]"
    
class ScriptedMockLLMAdapter(MockLLMAdapter):
    """
    Extended mock adapter with scripted response sequences.
    
    Use this when you need specific responses in a specific order,
    such as testing multi-turn conversations or complex scenarios.
    
    Usage:
        adapter = ScriptedMockLLMAdapter()
        adapter.queue_response('{"action_id": "go_north"}')
        adapter.queue_response('{"action_id": "take_key"}')
        # First call returns go_north, second returns take_key
    """
    
    def __init__(self, model: str = "scripted-mock"):
        super().__init__(model)
        self._response_queue: List[str] = []
    
    def queue_response(self, response: str) -> None:
        """Queue a response to be returned on the next LLM call."""
        self._response_queue.append(response)
    
    def queue_responses(self, responses: List[str]) -> None:
        """Queue multiple responses."""
        self._response_queue.extend(responses)
    
    def clear_queue(self) -> None:
        """Clear the response queue."""
        self._response_queue.clear()
    
    async def generate_response(self, prompt: str, **kwargs) -> str:
        """Return queued response if available, otherwise use parent behavior."""
        self._call_history.append({
            "method": "generate_response",
            "prompt": prompt[:200] + "..." if len(prompt) > 200 else prompt,
            "kwargs": kwargs
        })
        
        if self._response_queue:
            response = self._response_queue.pop(0)
            logger.debug(f"MockLLM: Returning queued response")
            return response
        
        return await super().generate_response(prompt, **kwargs)
    
    async def generate_text_response(self, prompt: str, system_prompt: str = None, **kwargs) -> str:
        """Return queued response if available, otherwise use parent behavior."""
        self._call_history.append({
            "method": "generate_text_response",
            "prompt": prompt[:200] + "..." if len(prompt) > 200 else prompt,
            "system_prompt": system_prompt,
            "kwargs": kwargs
        })
        
        if self._response_queue:
            response = self._response_queue.pop(0)
            logger.debug(f"MockLLM: Returning queued response")
            return response
        
        return await super().generate_text_response(prompt, system_prompt, **kwargs)

