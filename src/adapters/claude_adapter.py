"""
Claude adapter for the AI Native game engine.

Uses the Anthropic Python SDK to provide Claude LLM capabilities.
Also exposes an OpenAI-compatible shim via self.client so that
routes written for the OpenAI client (e.g. editor AI) keep working.
"""
from typing import Dict, List, Optional, Any
import logging
import json
import re
from dataclasses import dataclass

from anthropic import Anthropic, AsyncAnthropic
from src.adapters.utils.llm_metrics import build_llm_metrics, compact_metrics, now_ms
from src.core.interfaces import ILLMProvider

logger = logging.getLogger(__name__)

DEFAULT_CACHE_CONTROL = {"type": "ephemeral"}


def _resolve_cache_control(kwargs: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Pop and return the cache_control payload from kwargs."""
    return kwargs.pop("cache_control", DEFAULT_CACHE_CONTROL)


def _apply_cache_breakpoints(
    api_kwargs: Dict[str, Any],
    cache_control: Optional[Dict[str, Any]],
) -> None:
    """Annotate system and tools content blocks with cache_control breakpoints.

    Anthropic prompt caching requires cache_control on individual content
    blocks, not as a top-level API parameter.  This helper converts a plain
    system string to a content-block list and stamps the last system block
    (and, when present, the last tool definition) with the breakpoint.
    """
    if not cache_control:
        return

    system = api_kwargs.get("system")
    if isinstance(system, str):
        api_kwargs["system"] = [
            {"type": "text", "text": system, "cache_control": cache_control}
        ]
    elif isinstance(system, list) and system:
        system[-1] = {**system[-1], "cache_control": cache_control}

    tools = api_kwargs.get("tools")
    if isinstance(tools, list) and tools:
        tools[-1] = {**tools[-1], "cache_control": cache_control}


def _log_claude_metrics(
    *,
    model: str,
    operation: str,
    started_at_ms: float,
    usage: Any = None,
    **extra: Any,
) -> None:
    metrics = build_llm_metrics(
        provider="claude",
        model=model,
        operation=operation,
        started_at_ms=started_at_ms,
        usage=usage,
        extra=extra,
    )
    logger.info("LLM metrics: %s", json.dumps(compact_metrics(metrics), ensure_ascii=False, sort_keys=True))


# ---------------------------------------------------------------------------
# OpenAI-compatibility shim
# ---------------------------------------------------------------------------
# llm_routes.py calls  llm_provider.client.chat.completions.create(...)
# and inspects the response with OpenAI-shaped attribute access.  The thin
# wrapper below translates those calls into Anthropic SDK calls so that the
# rest of the codebase does not need to know which provider is active.
# ---------------------------------------------------------------------------

@dataclass
class _ToolCallFunction:
    name: str
    arguments: str  # JSON string


@dataclass
class _ToolCall:
    id: str
    function: _ToolCallFunction
    type: str = "function"


@dataclass
class _Message:
    content: Optional[str]
    tool_calls: Optional[List[_ToolCall]]
    role: str = "assistant"


@dataclass
class _Choice:
    message: _Message
    index: int = 0
    finish_reason: str = "stop"


@dataclass
class _Completion:
    choices: List[_Choice]


class _Completions:
    """Translates OpenAI chat.completions.create() → Anthropic messages.create()."""

    def __init__(self, anthropic_client: Anthropic, default_model: str):
        self._client = anthropic_client
        self._default_model = default_model

    @staticmethod
    def _openai_tools_to_anthropic(tools: List[Dict]) -> List[Dict]:
        converted = []
        for t in tools:
            fn = t.get("function", t)
            converted.append({
                "name": fn["name"],
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
            })
        return converted

    @staticmethod
    def _convert_messages(messages: List[Dict]):
        """Convert OpenAI-format messages to Anthropic format.

        Handles:
        - system messages → extracted as a separate system string
        - assistant messages with tool_calls → content array with tool_use blocks
        - tool messages → user messages with tool_result content blocks
        """
        system_parts: List[str] = []
        converted: List[Dict[str, Any]] = []

        for m in messages:
            role = m.get("role", "")

            if role == "system":
                system_parts.append(m["content"])

            elif role == "assistant":
                tool_calls = m.get("tool_calls")
                if tool_calls:
                    content_blocks: List[Dict[str, Any]] = []
                    if m.get("content"):
                        content_blocks.append({"type": "text", "text": m["content"]})
                    for tc in tool_calls:
                        fn = tc.get("function", {})
                        try:
                            inp = json.loads(fn.get("arguments", "{}"))
                        except (json.JSONDecodeError, TypeError):
                            inp = {}
                        content_blocks.append({
                            "type": "tool_use",
                            "id": tc.get("id", ""),
                            "name": fn.get("name", ""),
                            "input": inp,
                        })
                    converted.append({"role": "assistant", "content": content_blocks})
                else:
                    converted.append({"role": "assistant", "content": m.get("content") or ""})

            elif role == "tool":
                tool_result = {
                    "type": "tool_result",
                    "tool_use_id": m.get("tool_call_id", ""),
                    "content": m.get("content", ""),
                }
                # Anthropic requires alternating user/assistant turns.
                # Group consecutive tool results into one user message.
                if converted and converted[-1]["role"] == "user" and isinstance(converted[-1]["content"], list):
                    converted[-1]["content"].append(tool_result)
                else:
                    converted.append({"role": "user", "content": [tool_result]})

            else:
                converted.append({"role": role, "content": m.get("content", "")})

        system = "\n\n".join(system_parts) if system_parts else None
        return system, converted

    def create(self, *, model: str = None, messages: List[Dict],
               tools: List[Dict] = None, tool_choice: str = None,
               **kwargs) -> _Completion:
        model = model or self._default_model
        system, msgs = self._convert_messages(messages)
        started_at_ms = now_ms()

        api_kwargs: Dict[str, Any] = dict(
            model=model,
            messages=msgs,
            max_tokens=kwargs.pop("max_tokens", 8192),
        )
        cache_control = _resolve_cache_control(kwargs)
        if system:
            api_kwargs["system"] = system
        if tools:
            api_kwargs["tools"] = self._openai_tools_to_anthropic(tools)
        if tool_choice == "auto":
            api_kwargs["tool_choice"] = {"type": "auto"}
        _apply_cache_breakpoints(api_kwargs, cache_control)

        resp = self._client.messages.create(**api_kwargs)
        _log_claude_metrics(
            model=model,
            operation="chat.completions.create",
            started_at_ms=started_at_ms,
            usage=getattr(resp, "usage", None),
            stream=False,
            tools=bool(tools),
        )

        text_parts = []
        tool_calls = []
        for block in resp.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(_ToolCall(
                    id=block.id,
                    function=_ToolCallFunction(
                        name=block.name,
                        arguments=json.dumps(block.input),
                    ),
                ))

        content = "\n".join(text_parts) if text_parts else None
        finish = "tool_calls" if resp.stop_reason == "tool_use" else "stop"

        msg = _Message(
            content=content,
            tool_calls=tool_calls if tool_calls else None,
        )
        return _Completion(choices=[_Choice(message=msg, finish_reason=finish)])


class _Chat:
    def __init__(self, completions):
        self.completions = completions


class _OpenAIShim:
    """Minimal shim exposing  .chat.completions.create()  backed by Anthropic."""

    def __init__(self, anthropic_client: Anthropic, default_model: str):
        self.chat = _Chat(_Completions(anthropic_client, default_model))


# ---------------------------------------------------------------------------
# Async OpenAI-compatibility shim  (used by architect.py)
# ---------------------------------------------------------------------------
# architect.py calls:
#   await llm_provider.async_client.chat.completions.create(
#       ..., stream=True/False)
# and when streaming, iterates:
#   async for chunk in stream:
#       delta = chunk.choices[0].delta
#       delta.role / delta.content / delta.tool_calls
# ---------------------------------------------------------------------------

@dataclass
class _StreamDelta:
    role: Optional[str] = None
    content: Optional[str] = None
    tool_calls: Optional[list] = None


@dataclass
class _StreamChoice:
    delta: _StreamDelta
    index: int = 0


@dataclass
class _StreamChunk:
    choices: List[_StreamChoice]


@dataclass
class _StreamToolCallDelta:
    index: int
    id: Optional[str]
    function: Optional[_ToolCallFunction]


async def _anthropic_to_openai_stream(
    anthropic_stream,
    *,
    model: str,
    operation: str,
    started_at_ms: float,
    tools: bool,
):
    """Async generator that translates an Anthropic stream into OpenAI-shaped
    chunks, yielding each one as it arrives (true streaming)."""
    block_to_tool_idx: Dict[int, int] = {}
    next_tool_index = 0
    sent_role = False
    final_usage = None

    async with anthropic_stream as stream:
        async for event in stream:
            if event.type == "content_block_start":
                block = event.content_block
                if not sent_role:
                    yield _StreamChunk(choices=[_StreamChoice(
                        delta=_StreamDelta(role="assistant"))])
                    sent_role = True
                if block.type == "tool_use":
                    idx = next_tool_index
                    block_to_tool_idx[event.index] = idx
                    next_tool_index += 1
                    yield _StreamChunk(choices=[_StreamChoice(
                        delta=_StreamDelta(tool_calls=[_StreamToolCallDelta(
                            index=idx,
                            id=block.id,
                            function=_ToolCallFunction(name=block.name, arguments=""),
                        )]))])

            elif event.type == "content_block_delta":
                delta_obj = event.delta
                if delta_obj.type == "text_delta":
                    yield _StreamChunk(choices=[_StreamChoice(
                        delta=_StreamDelta(content=delta_obj.text))])
                elif delta_obj.type == "input_json_delta":
                    idx = block_to_tool_idx.get(event.index, next_tool_index - 1)
                    yield _StreamChunk(choices=[_StreamChoice(
                        delta=_StreamDelta(tool_calls=[_StreamToolCallDelta(
                            index=idx,
                            id=None,
                            function=_ToolCallFunction(name="", arguments=delta_obj.partial_json),
                        )]))])
        final_message_getter = getattr(stream, "get_final_message", None)
        if callable(final_message_getter):
            try:
                final_message = final_message_getter()
                if hasattr(final_message, "__await__"):
                    final_message = await final_message
                final_usage = getattr(final_message, "usage", None)
            except Exception:
                final_usage = None
    _log_claude_metrics(
        model=model,
        operation=operation,
        started_at_ms=started_at_ms,
        usage=final_usage,
        stream=True,
        tools=tools,
    )


class _AsyncCompletions:
    """Async version: translates OpenAI chat.completions.create() → Anthropic."""

    def __init__(self, async_anthropic_client: AsyncAnthropic, default_model: str):
        self._client = async_anthropic_client
        self._default_model = default_model

    async def create(self, *, model: str = None, messages: List[Dict],
                     tools: List[Dict] = None, tool_choice: str = None,
                     stream: bool = False, **kwargs):
        model = model or self._default_model
        system, msgs = _Completions._convert_messages(messages)
        started_at_ms = now_ms()

        api_kwargs: Dict[str, Any] = dict(
            model=model,
            messages=msgs,
            max_tokens=kwargs.pop("max_tokens", 8192),
        )
        cache_control = _resolve_cache_control(kwargs)
        if system:
            api_kwargs["system"] = system
        if tools:
            api_kwargs["tools"] = _Completions._openai_tools_to_anthropic(tools)
        if tool_choice == "auto":
            api_kwargs["tool_choice"] = {"type": "auto"}
        _apply_cache_breakpoints(api_kwargs, cache_control)

        if stream:
            anthropic_stream = self._client.messages.stream(**api_kwargs)
            return _anthropic_to_openai_stream(
                anthropic_stream,
                model=model,
                operation="chat.completions.create",
                started_at_ms=started_at_ms,
                tools=bool(tools),
            )

        resp = await self._client.messages.create(**api_kwargs)
        _log_claude_metrics(
            model=model,
            operation="chat.completions.create",
            started_at_ms=started_at_ms,
            usage=getattr(resp, "usage", None),
            stream=False,
            tools=bool(tools),
        )

        text_parts = []
        tool_calls = []
        for block in resp.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(_ToolCall(
                    id=block.id,
                    function=_ToolCallFunction(
                        name=block.name,
                        arguments=json.dumps(block.input),
                    ),
                ))

        content = "\n".join(text_parts) if text_parts else None
        finish = "tool_calls" if resp.stop_reason == "tool_use" else "stop"
        msg = _Message(content=content, tool_calls=tool_calls if tool_calls else None)
        return _Completion(choices=[_Choice(message=msg, finish_reason=finish)])


class _AsyncOpenAIShim:
    """Async shim exposing .chat.completions.create() backed by Anthropic."""

    def __init__(self, async_anthropic_client: AsyncAnthropic, default_model: str):
        self.chat = _Chat(_AsyncCompletions(async_anthropic_client, default_model))


# ---------------------------------------------------------------------------
# Main adapter
# ---------------------------------------------------------------------------

class ClaudeAdapter(ILLMProvider):
    """Adapter for Anthropic Claude models."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-6",
        timeout_connect: float = 10.0,
        timeout_read: float = 120.0,
    ):
        self.model = model

        timeout = timeout_connect + timeout_read

        self._anthropic = Anthropic(
            api_key=api_key,
            timeout=timeout,
            max_retries=2,
        )
        self._async_anthropic = AsyncAnthropic(
            api_key=api_key,
            timeout=timeout,
            max_retries=2,
        )

        self.client = _OpenAIShim(self._anthropic, model)
        self.async_client = _AsyncOpenAIShim(self._async_anthropic, model)

        logger.info(
            f"Claude adapter initialised — model: {model}, "
            f"timeout: {timeout}s"
        )

    # ---- helpers -----------------------------------------------------------

    @staticmethod
    def _split_system(messages: List[Dict]):
        system_parts, other = [], []
        for m in messages:
            if m["role"] == "system":
                system_parts.append(m["content"])
            else:
                other.append(m)
        return ("\n\n".join(system_parts) if system_parts else None), other

    @staticmethod
    def _openai_tools_to_anthropic(tools: List[Dict]) -> List[Dict]:
        out = []
        for t in tools:
            fn = t.get("function", t)
            out.append({
                "name": fn["name"],
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
            })
        return out

    def _extract_text(self, response) -> str:
        parts = [b.text for b in response.content if b.type == "text"]
        return "\n".join(parts)

    # ---- ILLMProvider implementation ---------------------------------------

    async def generate_response(self, prompt: str, **kwargs) -> str:
        try:
            kwargs.pop("response_format", None)
            started_at_ms = now_ms()
            cache_control = _resolve_cache_control(kwargs)

            api_kwargs: Dict[str, Any] = dict(
                model=self.model,
                max_tokens=kwargs.pop("max_tokens", 8192),
                system="You are a helpful assistant that only responds in valid JSON.",
                messages=[{"role": "user", "content": prompt}],
            )
            _apply_cache_breakpoints(api_kwargs, cache_control)
            resp = await self._async_anthropic.messages.create(**api_kwargs)
            _log_claude_metrics(
                model=self.model,
                operation="generate_response",
                started_at_ms=started_at_ms,
                usage=getattr(resp, "usage", None),
                stream=False,
                tools=False,
            )
            response = self._extract_text(resp)
            logger.info(f"Generated response: {response}")
            return response
        except Exception as e:
            logger.error(f"Failed to generate response: {e}")
            return f'{{"error": "Error generating response: {e}"}}'

    async def generate_text_response(self, prompt: str, system_prompt: str = None, **kwargs) -> str:
        try:
            started_at_ms = now_ms()
            api_kwargs: Dict[str, Any] = dict(
                model=self.model,
                max_tokens=kwargs.pop("max_tokens", 8192),
                messages=[{"role": "user", "content": prompt}],
            )
            cache_control = _resolve_cache_control(kwargs)
            if system_prompt:
                api_kwargs["system"] = system_prompt
            _apply_cache_breakpoints(api_kwargs, cache_control)

            resp = await self._async_anthropic.messages.create(**api_kwargs)
            _log_claude_metrics(
                model=self.model,
                operation="generate_text_response",
                started_at_ms=started_at_ms,
                usage=getattr(resp, "usage", None),
                stream=False,
                tools=False,
            )
            response = self._extract_text(resp)
            logger.info(f"Generated text response: {response[:100]}...")
            return response.strip()
        except Exception as e:
            logger.error(f"Failed to generate text response: {e}")
            return f"(Error generating response: {e})"

    async def generate_with_tools(self, prompt: str, system_prompt: str = None,
                                   tools: Optional[List[Dict]] = None, **kwargs) -> str:
        if tools is None:
            tools = self._get_default_game_tools()

        anthropic_tools = self._openai_tools_to_anthropic(tools)
        cache_control = _resolve_cache_control(kwargs)

        messages: List[Dict[str, Any]] = [{"role": "user", "content": prompt}]
        api_base: Dict[str, Any] = dict(
            model=self.model,
            max_tokens=kwargs.pop("max_tokens", 8192),
            tools=anthropic_tools,
        )
        if system_prompt:
            api_base["system"] = system_prompt
        _apply_cache_breakpoints(api_base, cache_control)

        max_iterations = 10
        for iteration in range(max_iterations):
            started_at_ms = now_ms()
            resp = await self._async_anthropic.messages.create(
                messages=messages, **api_base,
            )
            _log_claude_metrics(
                model=self.model,
                operation="generate_with_tools",
                started_at_ms=started_at_ms,
                usage=getattr(resp, "usage", None),
                stream=False,
                tools=True,
                iteration=iteration + 1,
            )

            tool_uses = [b for b in resp.content if b.type == "tool_use"]

            if not tool_uses:
                final = self._extract_text(resp)
                logger.info(
                    f"Generated response with tools (after {iteration + 1} iterations): "
                    f"{final[:100] if final else '(empty)'}..."
                )
                return final

            # Append the full assistant turn as-is
            messages.append({"role": "assistant", "content": resp.content})

            tool_results = []
            for tu in tool_uses:
                result = self._execute_tool_call_anthropic(tu)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": json.dumps(result),
                })
            messages.append({"role": "user", "content": tool_results})

        logger.warning(f"Max tool call iterations ({max_iterations}) reached")
        return self._extract_text(resp)

    # ---- tool execution ----------------------------------------------------

    def _get_default_game_tools(self) -> List[Dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "roll_dice",
                    "description": "Roll dice for skill checks, attack rolls, saving throws, damage, or any random outcome.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "dice": {
                                "type": "string",
                                "description": "Dice notation like '1d20', '2d6', '1d20+5'."
                            },
                            "reason": {
                                "type": "string",
                                "description": "Why the dice are being rolled."
                            },
                        },
                        "required": ["dice"],
                    },
                },
            }
        ]

    def _execute_tool_call_anthropic(self, tool_use_block) -> Dict[str, Any]:
        if tool_use_block.name == "roll_dice":
            return self._execute_dice_roll(tool_use_block.input)
        logger.warning(f"Unknown tool: {tool_use_block.name}")
        return {"error": f"Unknown tool: {tool_use_block.name}"}

    def _execute_dice_roll(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        from src.utils.dice_roller import roll_dice

        dice_notation = arguments.get("dice", "1d20")
        reason = arguments.get("reason", "")
        try:
            result = roll_dice(dice_notation)
            logger.info(f"Dice roll: {dice_notation} = {result} (reason: {reason})")
            return {"dice": dice_notation, "result": result, "reason": reason}
        except ValueError as e:
            logger.error(f"Invalid dice notation '{dice_notation}': {e}")
            return {"dice": dice_notation, "error": str(e), "reason": reason}

