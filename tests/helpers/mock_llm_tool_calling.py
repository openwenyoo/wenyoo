"""Tool-calling MockLLM — the Phase-0 blocker (see test-harness-rollout.md §5.4).

``MockLLMAdapter`` only implements ``generate_response`` / ``generate_text_response``,
neither of which the Architect uses. The Architect drives the LLM through
``llm_provider.async_client.chat.completions.create(...)`` and consumes an
OpenAI-shaped response (``.choices[0].message.tool_calls`` etc.). This module
provides a scripted stand-in that exposes exactly that surface — in BOTH the
non-streaming form (returns a ``_Completion``) and the streaming form
(``stream=True`` → async iterator of chunks), because any frontend-attached run
takes the streaming branch (architect.py:528).

The response/chunk object shapes mirror ``src/adapters/claude_adapter.py``; we
use ``SimpleNamespace`` so ``Architect._msg_to_dict`` takes its non-pydantic
branch (it special-cases ``SimpleNamespace``).

Usage::

    llm = ToolCallingMockLLM()
    llm.queue_tool_calls([tc("commit", artifacts=[...], state_changes={...})])
    # ... drive the Architect ...
    assert llm.captured_calls()[-1].tool_choice == "auto"
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, AsyncIterator, Dict, List, Optional
from uuid import uuid4

from src.core.interfaces import ILLMProvider


# ── Test-author helpers ──────────────────────────────────────────────────────

def tc(name: str, **args: Any) -> dict:
    """Build one tool_call dict in OpenAI format.

    >>> tc("roll_dice", dice="1d20", reason="test")["function"]["name"]
    'roll_dice'
    """
    return {
        "id": f"call_{uuid4().hex[:8]}",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)},
    }


@dataclass
class CapturedCall:
    """One ``.create()`` invocation, captured for assertions."""
    messages: List[dict]
    tools: Optional[List[dict]]
    tool_choice: Optional[str]
    model: Optional[str]
    stream: bool


# ── Internal: a single queued turn ───────────────────────────────────────────

class _QueuedResponse:
    def __init__(
        self,
        tool_calls: Optional[List[dict]] = None,
        content: Optional[str] = None,
        finish_reason: Optional[str] = None,
    ):
        self.tool_calls = tool_calls
        self.content = content
        if finish_reason is not None:
            self.finish_reason = finish_reason
        elif tool_calls:
            self.finish_reason = "tool_calls"
        else:
            self.finish_reason = "stop"


def _to_tool_call_obj(d: dict) -> SimpleNamespace:
    fn = d.get("function", {})
    return SimpleNamespace(
        id=d.get("id") or f"call_{uuid4().hex[:8]}",
        type="function",
        function=SimpleNamespace(
            name=fn.get("name", ""),
            arguments=fn.get("arguments", "{}"),
        ),
    )


def _build_message(spec: _QueuedResponse) -> SimpleNamespace:
    tool_calls = (
        [_to_tool_call_obj(d) for d in spec.tool_calls] if spec.tool_calls else None
    )
    return SimpleNamespace(role="assistant", content=spec.content, tool_calls=tool_calls)


def _chunk(delta: SimpleNamespace, finish_reason: Optional[str]) -> SimpleNamespace:
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta, finish_reason=finish_reason)])


async def _stream_from_spec(spec: _QueuedResponse) -> AsyncIterator[SimpleNamespace]:
    """Emit OpenAI-shaped streaming chunks for one queued turn.

    Tool-call ``arguments`` are split across two chunks on purpose so the
    Architect's incremental narrative extractors actually run.
    """
    # Opening role chunk.
    yield _chunk(SimpleNamespace(role="assistant", content=None, tool_calls=None), None)

    if spec.tool_calls:
        for idx, d in enumerate(spec.tool_calls):
            fn = d.get("function", {})
            # Chunk 1: id + function name (arguments empty).
            yield _chunk(
                SimpleNamespace(role=None, content=None, tool_calls=[
                    SimpleNamespace(
                        index=idx,
                        id=d.get("id") or f"call_{idx}",
                        type="function",
                        function=SimpleNamespace(name=fn.get("name", ""), arguments=""),
                    )
                ]),
                None,
            )
            # Chunks 2..n: argument fragments (at least two non-empty pieces).
            args = fn.get("arguments", "{}") or ""
            mid = max(1, len(args) // 2)
            for frag in (args[:mid], args[mid:]):
                if not frag:
                    continue
                yield _chunk(
                    SimpleNamespace(role=None, content=None, tool_calls=[
                        SimpleNamespace(
                            index=idx,
                            id=None,
                            type="function",
                            function=SimpleNamespace(name=None, arguments=frag),
                        )
                    ]),
                    None,
                )
        yield _chunk(SimpleNamespace(role=None, content=None, tool_calls=None), "tool_calls")
    else:
        if spec.content:
            yield _chunk(
                SimpleNamespace(role=None, content=spec.content, tool_calls=None), None
            )
        yield _chunk(SimpleNamespace(role=None, content=None, tool_calls=None), spec.finish_reason)


# ── OpenAI-shaped async client surface ───────────────────────────────────────

class _Completions:
    def __init__(self, owner: "ToolCallingMockLLM"):
        self._owner = owner

    async def create(
        self,
        *,
        model: Optional[str] = None,
        messages: Optional[List[dict]] = None,
        tools: Optional[List[dict]] = None,
        tool_choice: Optional[str] = None,
        stream: bool = False,
        **_: Any,
    ):
        self._owner._captured.append(
            CapturedCall(
                messages=copy.deepcopy(messages) if messages is not None else [],
                tools=tools,
                tool_choice=tool_choice,
                model=model,
                stream=stream,
            )
        )
        spec = self._owner._queue.pop(0) if self._owner._queue else _QueuedResponse()

        if stream:
            # An async-generator object is itself the async iterator the
            # Architect consumes via ``async for chunk in stream``.
            return _stream_from_spec(spec)

        msg = _build_message(spec)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=msg, finish_reason=spec.finish_reason)]
        )


class _Chat:
    def __init__(self, owner: "ToolCallingMockLLM"):
        self.completions = _Completions(owner)


class _AsyncClient:
    def __init__(self, owner: "ToolCallingMockLLM"):
        self.chat = _Chat(owner)


# ── The provider ─────────────────────────────────────────────────────────────

class ToolCallingMockLLM(ILLMProvider):
    """Scripted ILLMProvider that the Architect can actually drive.

    Each ``queue_*`` call appends one *turn*; the Architect consumes one turn
    per LLM round-trip. If the queue empties, ``.create()`` returns a bare
    no-tool-call response so the Architect loop terminates gracefully instead
    of hanging.
    """

    def __init__(self, model: str = "mock"):
        self.model = model
        self._queue: List[_QueuedResponse] = []
        self._captured: List[CapturedCall] = []
        self.async_client = _AsyncClient(self)

    # legacy ILLMProvider surface (unused by Architect, required by interface)
    async def generate_response(self, prompt: str, **kwargs: Any) -> str:
        return ""

    async def generate_text_response(
        self, prompt: str, system_prompt: Optional[str] = None, **kwargs: Any
    ) -> str:
        return ""

    # test-author surface
    def queue_tool_calls(self, calls: List[dict]) -> "ToolCallingMockLLM":
        """Next ``.create()`` returns a response with these tool_calls."""
        self._queue.append(_QueuedResponse(tool_calls=list(calls)))
        return self

    def queue_text(self, content: str) -> "ToolCallingMockLLM":
        """Next ``.create()`` returns plain content, no tool_calls."""
        self._queue.append(_QueuedResponse(content=content))
        return self

    def queue_finish(self, *, content: str = "", reason: str = "stop") -> "ToolCallingMockLLM":
        """Next ``.create()`` returns content with a custom finish_reason."""
        self._queue.append(_QueuedResponse(content=content, finish_reason=reason))
        return self

    def captured_calls(self) -> List[CapturedCall]:
        """All ``.create()`` invocations, oldest first."""
        return list(self._captured)

    @property
    def queue_size(self) -> int:
        return len(self._queue)

    def clear(self) -> None:
        self._queue.clear()
        self._captured.clear()
