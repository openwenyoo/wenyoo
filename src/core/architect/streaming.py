"""_StreamingMixin"""
from types import SimpleNamespace
from typing import Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from src.models.game_state import GameState


class _StreamingMixin:
    """Collect streamed LLM responses for authoritative tool dispatch."""

    async def _streaming_llm_call(
        self, llm_provider, messages: list, game_state: 'GameState',
        player_id: str, ctx: Dict
    ):
        """Collect tool arguments before committing or delivering their text.

        Audience fields may arrive after payload text, and a commit can fail
        validation. Only _deliver_artifacts can safely route an accepted
        narrative to players; forwarding partial arguments leaks private text.
        """
        stream = await llm_provider.async_client.chat.completions.create(
            model=llm_provider.model,
            messages=messages,
            tools=self._tool_definitions,
            tool_choice="auto",
            stream=True,
        )

        content_parts = []
        reasoning_parts = []  # thinking-mode models stream reasoning_content
        tool_calls_map = {}  # index -> {id, function_name, arguments}
        role = None

        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta is None:
                continue

            if delta.role:
                role = delta.role

            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_calls_map:
                        tool_calls_map[idx] = {
                            "id": tc_delta.id or "",
                            "function_name": "",
                            "arguments": "",
                        }
                    entry = tool_calls_map[idx]
                    if tc_delta.id:
                        entry["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            entry["function_name"] = tc_delta.function.name
                        if tc_delta.function.arguments:
                            entry["arguments"] += tc_delta.function.arguments

            if delta.content:
                content_parts.append(delta.content)

            # Thinking-mode models (e.g. DeepSeek) stream a separate
            # reasoning_content channel that must be echoed back on the
            # assistant turn that carries the resulting tool_calls.
            delta_reasoning = getattr(delta, "reasoning_content", None)
            if delta_reasoning:
                reasoning_parts.append(delta_reasoning)

        full_content = "".join(content_parts) if content_parts else None
        full_reasoning = "".join(reasoning_parts) if reasoning_parts else None

        if tool_calls_map:
            tool_calls_list = []
            for idx in sorted(tool_calls_map.keys()):
                entry = tool_calls_map[idx]
                tc = SimpleNamespace(
                    id=entry["id"],
                    function=SimpleNamespace(
                        name=entry["function_name"],
                        arguments=entry["arguments"],
                    ),
                    type="function",
                )
                tool_calls_list.append(tc)
            response_msg = SimpleNamespace(
                role=role or "assistant",
                content=full_content,
                tool_calls=tool_calls_list,
                reasoning_content=full_reasoning,
            )
        else:
            response_msg = SimpleNamespace(
                role=role or "assistant",
                content=full_content,
                tool_calls=None,
                reasoning_content=full_reasoning,
            )

        return response_msg
