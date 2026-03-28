"""
Ollama adapter for the AI Native game engine.

This module implements the adapter for the Ollama API,
providing language model capabilities to the game engine.
"""
from collections import OrderedDict
from typing import Dict, List, Optional, Any
import logging
import json
import re
import requests
from src.adapters.utils.llm_metrics import build_llm_metrics, compact_metrics, now_ms
from src.core.interfaces import ILLMProvider

logger = logging.getLogger(__name__)


class OllamaAdapter(ILLMProvider):
    """Adapter for the Ollama API."""
    
    def __init__(
        self, 
        base_url: str = "http://localhost:11434", 
        model: str = "llama2",
        timeout_connect: float = 30.0,
        timeout_read: float = 120.0
    ):
        """Initialize the Ollama adapter.
        
        Args:
            base_url (str, optional): Base URL for the Ollama API. Defaults to "http://localhost:11434".
            model (str, optional): Model to use. Defaults to "llama2".
            timeout_connect (float, optional): Connection timeout in seconds. Defaults to 30.0.
            timeout_read (float, optional): Read timeout in seconds. Defaults to 120.0.
        """
        self.base_url = base_url
        self.model = model
        self.api_url = f"{base_url}/api/generate"
        self.timeout_connect = timeout_connect
        self.timeout_read = timeout_read
        self._max_contexts = 32
        self._contexts: OrderedDict[str, Any] = OrderedDict()
        
        logger.info(f"Ollama adapter initialized with model: {model}")

    def _log_request_metrics(self, operation: str, started_at_ms: float, usage: Any = None, **extra: Any) -> None:
        metrics = build_llm_metrics(
            provider="ollama",
            model=self.model,
            operation=operation,
            started_at_ms=started_at_ms,
            usage=usage,
            extra=extra,
        )
        logger.info("LLM metrics: %s", json.dumps(compact_metrics(metrics), ensure_ascii=False, sort_keys=True))

    @staticmethod
    def _context_key_from_kwargs(kwargs: Dict[str, Any]) -> Optional[str]:
        context_key = kwargs.pop("context_key", None) or kwargs.pop("session_id", None)
        return str(context_key) if context_key else None

    def _build_payload(
        self,
        prompt: str,
        *,
        context_key: Optional[str],
        request_options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }
        if context_key and context_key in self._contexts:
            payload["context"] = self._contexts[context_key]
        if isinstance(request_options, dict):
            for key in ("options", "keep_alive", "raw", "format", "system", "template"):
                if key in request_options:
                    payload[key] = request_options[key]
        return payload

    def _remember_context(self, context_key: Optional[str], result: Dict[str, Any]) -> None:
        if context_key and result.get("context") is not None:
            self._contexts.pop(context_key, None)
            self._contexts[context_key] = result["context"]
            while len(self._contexts) > self._max_contexts:
                self._contexts.popitem(last=False)
    
    async def generate_response(self, prompt: str, constraints: Dict[str, Any] = None) -> str:
        """Generate a response based on a prompt and constraints.

        Args:
            prompt (str): The prompt to generate a response for.
            constraints (Dict[str, Any]): Constraints on the generation.

        Returns:
            str: The generated response.
        """
        try:
            started_at_ms = now_ms()
            request_options = dict(constraints or {})
            context_key = self._context_key_from_kwargs(request_options)
            result = await self._send_async_request(
                prompt,
                context_key=context_key,
                request_options=request_options,
            )
            self._remember_context(context_key, result)
            response = result.get("response", "")
            # Strip the thinking process from the response
            response = re.sub(r'<think>[\s\S]*?</think>', '', response, flags=re.IGNORECASE).strip()
            # Strip markdown code blocks
            response = re.sub(r'```(json|yaml)?\n', '', response)
            response = re.sub(r'```', '', response).strip()
            self._log_request_metrics(
                "generate_response",
                started_at_ms,
                result,
                stream=False,
                tools=False,
                prompt_chars=len(prompt),
                response_chars=len(response),
                context_key=context_key,
            )
            logger.info(f"Generated and cleaned response: {response}")
            return response

        except Exception as e:
            logger.error(f"Failed to generate response: {e}")
            return f"Error generating response: {e}"

    async def generate_text_response(self, prompt: str, system_prompt: str = None, **kwargs) -> str:
        """Generate a plain text response."""
        combined_prompt = prompt if not system_prompt else f"{system_prompt}\n\n{prompt}"
        return await self.generate_response(combined_prompt, constraints=kwargs or None)
    
    def _send_request(
        self,
        prompt: str,
        *,
        context_key: Optional[str] = None,
        request_options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Send a request to the Ollama API.
        
        Args:
            prompt (str): The prompt to send.
            
        Returns:
            str: The response from the API.
        """
        try:
            payload = self._build_payload(
                prompt,
                context_key=context_key,
                request_options=request_options,
            )
            
            # Send request with timeout
            response = requests.post(
                self.api_url, 
                json=payload,
                timeout=(self.timeout_connect, self.timeout_read)
            )
            response.raise_for_status()
            
            # Parse response
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Ollama API request failed: {e}")
            raise
    
    async def _send_async_request(
        self,
        prompt: str,
        *,
        context_key: Optional[str] = None,
        request_options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Send an async request to Ollama API."""
        try:
            import aiohttp
            timeout = aiohttp.ClientTimeout(
                connect=self.timeout_connect,
                total=self.timeout_connect + self.timeout_read
            )
            async with aiohttp.ClientSession(timeout=timeout) as session:
                data = self._build_payload(
                    prompt,
                    context_key=context_key,
                    request_options=request_options,
                )
                async with session.post(self.api_url, json=data) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        logger.error(f"Ollama API error: {response.status}")
                        return {}
        except Exception as e:
            logger.error(f"Error calling Ollama API: {e}")
            # Fallback to sync request
            return self._send_request(
                prompt,
                context_key=context_key,
                request_options=request_options,
            )
    