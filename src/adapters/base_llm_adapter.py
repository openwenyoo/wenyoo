"""
OpenAI-compatible LLM adapter for the AI Native game engine.

This module provides the shared provider implementation for OpenAI-compatible
APIs such as OpenAI, DashScope, and vLLM endpoints.
"""
from typing import Dict, List, Optional, Any
import logging
import json
from src.core.interfaces import ILLMProvider
from openai import OpenAI, AsyncOpenAI
import httpx
from src.adapters.utils.llm_metrics import build_llm_metrics, compact_metrics, now_ms

logger = logging.getLogger(__name__)


class BaseLLMAdapter(ILLMProvider):
    """Adapter for OpenAI-compatible APIs (OpenAI, DashScope, vLLM, etc.)."""
    
    def __init__(
        self, 
        api_key: str, 
        base_url: str, 
        model: str = "qwen-plus-latest",
        timeout_connect: float = 10.0,
        timeout_read: float = 120.0
    ):
        self.model = model
        
        # Configure timeout to handle slow API providers
        # Use shorter connect timeout for faster retries if first connection fails
        timeout = httpx.Timeout(
            connect=timeout_connect,
            read=timeout_read,
            write=timeout_read,
            pool=timeout_read
        )
        
        # Create custom HTTP client with HTTP/1.1 only
        # This avoids HTTP/2 connection negotiation issues that can cause
        # first-request delays with some API providers
        http_client = httpx.Client(
            timeout=timeout,
            http2=False,  # Force HTTP/1.1 for more reliable connections
        )
        
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            http_client=http_client,
        )
        
        async_timeout = httpx.Timeout(
            connect=timeout_connect,
            read=timeout_read,
            write=timeout_read,
            pool=timeout_read
        )
        async_http_client = httpx.AsyncClient(
            timeout=async_timeout,
            http2=False,
        )
        self.async_client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            http_client=async_http_client,
        )
        
        logger.info(
            f"OpenAI compatible adapter initialized with model: {model}, "
            f"timeout: connect={timeout_connect}s, read={timeout_read}s"
        )

    @staticmethod
    def _apply_provider_options(kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Map optional provider-specific tuning knobs into OpenAI SDK kwargs."""
        provider_options = kwargs.pop("provider_options", None) or {}
        if not isinstance(provider_options, dict):
            return kwargs

        cache_control = provider_options.get("cache_control")
        extra_body = provider_options.get("extra_body")
        extra_headers = provider_options.get("extra_headers")
        extra_query = provider_options.get("extra_query")

        if cache_control is not None:
            merged_body = dict(kwargs.get("extra_body") or {})
            merged_body.setdefault("cache_control", cache_control)
            kwargs["extra_body"] = merged_body
        if isinstance(extra_body, dict):
            merged_body = dict(kwargs.get("extra_body") or {})
            merged_body.update(extra_body)
            kwargs["extra_body"] = merged_body
        if isinstance(extra_headers, dict):
            merged_headers = dict(kwargs.get("extra_headers") or {})
            merged_headers.update(extra_headers)
            kwargs["extra_headers"] = merged_headers
        if isinstance(extra_query, dict):
            merged_query = dict(kwargs.get("extra_query") or {})
            merged_query.update(extra_query)
            kwargs["extra_query"] = merged_query
        return kwargs

    def _log_request_metrics(self, operation: str, started_at_ms: float, usage: Any = None, **extra: Any) -> None:
        metrics = build_llm_metrics(
            provider="openai-compatible",
            model=self.model,
            operation=operation,
            started_at_ms=started_at_ms,
            usage=usage,
            extra=extra,
        )
        logger.info("LLM metrics: %s", json.dumps(compact_metrics(metrics), ensure_ascii=False, sort_keys=True))
    
    async def generate_response(self, prompt: str, **kwargs) -> str:
        """Generate a response based on a prompt (JSON mode)."""
        try:
            started_at_ms = now_ms()
            kwargs['response_format'] = {"type": "json_object"}
            kwargs = self._apply_provider_options(kwargs)

            completion = await self.async_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that only responds in valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                **kwargs
            )
            self._log_request_metrics("generate_response", started_at_ms, completion.usage, tools=False, stream=False)
            response = completion.choices[0].message.content
            logger.info(f"Generated response: {response}")
            return response

        except Exception as e:
            logger.error(f"Failed to generate response: {e}")
            return f"{{\"error\": \"Error generating response: {e}\"}}"
    
    async def generate_text_response(self, prompt: str, system_prompt: str = None, **kwargs) -> str:
        """Generate a plain text response (no JSON mode)."""
        try:
            started_at_ms = now_ms()
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            kwargs = self._apply_provider_options(kwargs)

            completion = await self.async_client.chat.completions.create(
                model=self.model,
                messages=messages,
                **kwargs
            )
            self._log_request_metrics("generate_text_response", started_at_ms, completion.usage, tools=False, stream=False)
            response = completion.choices[0].message.content
            logger.info(f"Generated text response: {response[:100]}...")
            return response.strip()

        except Exception as e:
            logger.error(f"Failed to generate text response: {e}")
            return f"(Error generating response: {e})"

    async def generate_with_tools(self, prompt: str, system_prompt: str = None, 
                                   tools: Optional[List[Dict]] = None, **kwargs) -> str:
        """Generate a response with tool calling support.
        
        This method allows the LLM to call tools (like dice rolling) during generation.
        The LLM decides when to call tools based on the context.
        
        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt
            tools: Optional list of tool definitions. If None, uses default game tools.
            **kwargs: Additional arguments passed to the API
            
        Returns:
            The final response content after all tool calls are resolved
        """
        # Default game tools if none provided
        if tools is None:
            tools = self._get_default_game_tools()
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        try:
            # Loop to handle multiple tool calls
            max_iterations = 10  # Prevent infinite loops
            iteration = 0
            kwargs = self._apply_provider_options(kwargs)
            
            while iteration < max_iterations:
                iteration += 1
                started_at_ms = now_ms()
                
                completion = await self.async_client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    **kwargs
                )
                self._log_request_metrics(
                    "generate_with_tools",
                    started_at_ms,
                    completion.usage,
                    tools=True,
                    stream=False,
                    iteration=iteration,
                )
                
                response_message = completion.choices[0].message
                
                if response_message.tool_calls:
                    messages.append(response_message)
                    
                    for tool_call in response_message.tool_calls:
                        tool_result = self._execute_tool_call(tool_call)
                        
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(tool_result)
                        })
                    
                    continue
                else:
                    final_response = response_message.content
                    logger.info(f"Generated response with tools (after {iteration} iterations): {final_response[:100] if final_response else '(empty)'}...")
                    return final_response if final_response else ""
            
            # Max iterations reached
            logger.warning(f"Max tool call iterations ({max_iterations}) reached")
            return response_message.content if response_message.content else ""
            
        except Exception as e:
            logger.error(f"Failed to generate response with tools: {e}", exc_info=True)
            return f'{{"error": "Error generating response: {e}"}}'

    def _get_default_game_tools(self) -> List[Dict]:
        """Get the default game tools for tool calling.
        
        Returns:
            List of tool definitions in OpenAI format
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": "roll_dice",
                    "description": "Roll dice for skill checks, attack rolls, saving throws, damage, or any random outcome. Use standard dice notation.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "dice": {
                                "type": "string",
                                "description": "Dice notation like '1d20', '2d6', '1d20+5', '3d8-2'. Format: NdS+M where N=number of dice, S=sides, M=modifier"
                            },
                            "reason": {
                                "type": "string",
                                "description": "Why the dice are being rolled (e.g., 'Strength check to break door', 'Attack roll against goblin')"
                            }
                        },
                        "required": ["dice"]
                    }
                }
            }
        ]

    def _execute_tool_call(self, tool_call) -> Dict[str, Any]:
        """Execute a tool call and return the result.
        
        Args:
            tool_call: The tool call object from the API response
            
        Returns:
            Dict with the tool execution result
        """
        function_name = tool_call.function.name
        
        try:
            arguments = json.loads(tool_call.function.arguments)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse tool arguments: {e}")
            return {"error": f"Invalid arguments: {e}"}
        
        if function_name == "roll_dice":
            return self._execute_dice_roll(arguments)
        else:
            logger.warning(f"Unknown tool: {function_name}")
            return {"error": f"Unknown tool: {function_name}"}

    def _execute_dice_roll(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a dice roll tool call.
        
        Args:
            arguments: Dict with 'dice' (required) and 'reason' (optional)
            
        Returns:
            Dict with roll result and details
        """
        from src.utils.dice_roller import roll_dice
        
        dice_notation = arguments.get("dice", "1d20")
        reason = arguments.get("reason", "")
        
        try:
            result = roll_dice(dice_notation)
            logger.info(f"Dice roll: {dice_notation} = {result} (reason: {reason})")
            return {
                "dice": dice_notation,
                "result": result,
                "reason": reason
            }
        except ValueError as e:
            logger.error(f"Invalid dice notation '{dice_notation}': {e}")
            return {
                "dice": dice_notation,
                "error": str(e),
                "reason": reason
            }
    