"""
Architect Agent - Unified LLM agent for the AI Native game engine.

The Architect is a single LLM agent that replaces all scattered LLM call sites.
It operates inside a tool-calling loop with two categories of tools:

- Read Tools (agentic search) -- query game state to gather context
- Write Tools (effects/actions) -- act on the world, including sending text to the player

Key insight: the Architect calls `commit_world_event` as a tool mid-loop, atomically
narrating to the player AND applying state changes in a single call.
"""

import json
import logging
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.game_kernel import GameKernel
    from src.models.game_state import GameState
    from src.models.story_models import Story

logger = logging.getLogger(__name__)

from src.core.architect.task import (
    ArchitectTask,
    infer_task_profile,
    TASK_PROFILE_WORLD_ACTION,
    TASK_PROFILE_PERCEPTION_RENDER,
    TASK_PROFILE_WORKFLOW,
    TASK_PROFILE_BACKGROUND_SIMULATION,
    ARTIFACT_KIND_NARRATIVE,
)
from src.core.architect.streaming import _StreamingMixin
from src.core.architect.delivery import _DeliveryMixin
from src.core.architect.tools import _ToolMixin
from src.core.architect.prompts import _PromptMixin


# ═══════════════════════════════════════════════════════════════════════════════
# Architect Agent
# ═══════════════════════════════════════════════════════════════════════════════

class Architect(_PromptMixin, _ToolMixin, _DeliveryMixin, _StreamingMixin):
    """
    Unified LLM agent that manages all LLM-generated content in the story world.
    
    Operates via a tool-calling loop:
    1. Receives a task (player input, perception render, event)
    2. Builds system prompt + world index + task message
    3. Enters tool-calling loop with the LLM
    4. LLM calls Read tools to gather context, then Write tools to act
    5. commit_world_event delivers narrative AND state changes atomically
    6. Deferred world-enrichment can happen in later background passes
    """

    def __init__(self, game_kernel: 'GameKernel'):
        self.game_kernel = game_kernel
        self._tool_registry: Dict[str, Callable] = {}
        self._tool_definitions: List[Dict] = []
        self._register_tools()
        self._system_prompt: Optional[str] = None

    def _normalize_task_contract(self, task: ArchitectTask) -> ArchitectTask:
        """Fill task contract defaults so callers do not need to set profiles directly."""
        task.task_profile = infer_task_profile(task.task_type, task.task_profile)
        return task

    # ═══════════════════════════════════════════════════════════════════════════
    # Tool Registration
    # ═══════════════════════════════════════════════════════════════════════════



    # ═══════════════════════════════════════════════════════════════════════════
    # Main Entry Point
    # ═══════════════════════════════════════════════════════════════════════════

    async def handle(self, task: ArchitectTask, game_state: 'GameState',
                     player_id: str, story: 'Story') -> Dict[str, Any]:
        """
        Main entry point. Builds context, runs tool-calling loop.
        
        Returns the execution context so callers like DSPP scene refresh can
        inspect captured output without persisting it as authoritative state.
        
        Args:
            task: What the Architect should do
            game_state: Current game state
            player_id: The player's ID
            story: The story definition
        """
        task = self._normalize_task_contract(task)
        system_prompt = self._get_system_prompt()
        world_index = self._build_world_index(game_state, player_id, story)
        user_prompt = self._build_task_prompt(task, world_index, game_state, player_id)

        logger.info(f"Architect handling task: {task.task_type} for player {player_id}")
        # Log the task-specific portion of the prompt (skip world_index which is long)
        # The task content starts after the world_index section
        task_section_start = user_prompt.find("## ")
        if task_section_start >= 0:
            task_section = user_prompt[task_section_start:]
            task_preview = task_section[:4000] + "..." if len(task_section) > 4000 else task_section
            logger.debug(f"Architect task prompt (task section, {len(user_prompt)} chars total):\n{task_preview}")
        else:
            prompt_preview = user_prompt[:1500] + "..." if len(user_prompt) > 1500 else user_prompt
            logger.debug(f"Architect task prompt ({len(user_prompt)} chars total):\n{prompt_preview}")

        ctx = {
            "game_state": game_state,
            "player_id": player_id,
            "story": story,
            "displayed_messages": [],
            "world_events": [],
            "structured_results": [],
            "artifacts": [],
            "task_type": task.task_type,
            "task_profile": task.task_profile,
        }
        ctx.update(task.extra_context)

        await self._run_tool_loop(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            game_state=game_state,
            player_id=player_id,
            story=story,
            ctx=ctx,
        )

        needs_display = task.task_type == "player_input"
        turn_handled = bool(ctx["displayed_messages"]) or bool(ctx.get("presented_form"))
        if needs_display and not turn_handled:
            logger.warning(
                f"Architect completed {task.task_type} without any commit_world_event "
                "-- sending fallback message to player"
            )
            fallback = "*The world seems to pause for a moment, then continues as before.*"
            await self._send_text_to_player(fallback, player_id, "game")
            game_state.add_message_to_history(
                role="companion",
                content=fallback,
                player_ids=[player_id],
                location=game_state.get_player_location(player_id),
                metadata={"event_type": "architect_fallback", "message_type": "game"},
            )

        return ctx

    # ═══════════════════════════════════════════════════════════════════════════
    # Tool-Calling Loop
    # ═══════════════════════════════════════════════════════════════════════════

    async def _run_tool_loop(self, system_prompt: str, user_prompt: str,
                              game_state: 'GameState', player_id: str,
                              story: 'Story', ctx: Optional[Dict] = None) -> None:
        """Run the Architect's tool-calling loop.

        The Architect controls all narrative and world-state changes through
        tool calls.  All player-facing text goes through commit_world_event
        -- the LLM's bare text content is never sent to the player.
        """
        llm_provider = self.game_kernel.llm_provider
        if not llm_provider:
            logger.error("Architect: no LLM provider available")
            return

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        if ctx is None:
            ctx = {
                "game_state": game_state,
                "player_id": player_id,
                "story": story,
                "displayed_messages": [],
            }

        # T1A: Pre-inject read_game_state result so the LLM can skip its
        # first round-trip and go directly to commit_world_event.
        # TODO(graph-context): Swap this heuristic local preload for compiled
        # graph-neighborhood retrieval once the story graph / runtime overlay
        # pipeline exists.
        task_profile = ctx.get("task_profile", TASK_PROFILE_WORLD_ACTION)
        if task_profile in (
            TASK_PROFILE_WORLD_ACTION,
            TASK_PROFILE_PERCEPTION_RENDER,
            TASK_PROFILE_WORKFLOW,
            TASK_PROFILE_BACKGROUND_SIMULATION,
        ):
            preload_id = "preloaded_read_game_state_local"
            gs_result = self._tool_read_game_state_sync(
                game_state,
                player_id,
                story,
                view="local",
                max_history=4,
            )

            def _safe_default_pre(obj):
                if hasattr(obj, 'model_dump'):
                    return obj.model_dump()
                return str(obj)
            gs_json = json.dumps(gs_result, ensure_ascii=False, default=_safe_default_pre)

            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": preload_id,
                    "type": "function",
                    "function": {
                        "name": "read_game_state",
                        "arguments": "{\"view\":\"local\",\"max_history\":4}",
                    }
                }]
            })
            messages.append({
                "role": "tool",
                "tool_call_id": preload_id,
                "content": gs_json,
            })
            logger.debug("Architect: pre-injected local read_game_state (%d chars)", len(gs_json))

        max_iterations = 12
        use_streaming_api = self.game_kernel.frontend_adapter is not None
        for iteration in range(max_iterations):
            try:
                if use_streaming_api:
                    try:
                        response_msg = await self._streaming_llm_call(
                            llm_provider, messages, game_state, player_id, ctx
                        )
                    except Exception as stream_err:
                        logger.warning(f"Streaming call failed, falling back to non-streaming: {stream_err}")
                        completion = await llm_provider.async_client.chat.completions.create(
                            model=llm_provider.model,
                            messages=messages,
                            tools=self._tool_definitions,
                            tool_choice="auto",
                        )
                        response_msg = completion.choices[0].message
                else:
                    completion = await llm_provider.async_client.chat.completions.create(
                        model=llm_provider.model,
                        messages=messages,
                        tools=self._tool_definitions,
                        tool_choice="auto",
                    )
                    response_msg = completion.choices[0].message

                if not response_msg.tool_calls:
                    # TODO: This fallback exists because some LLMs fail to call
                    # commit_world_event and instead return bare text. Ideally the
                    # LLM should always use commit_world_event; remove this when
                    # models are reliable enough to follow tool-calling instructions.
                    if response_msg.content and not ctx["displayed_messages"]:
                        bare = response_msg.content
                        logger.warning(
                            "Architect [%d] returned bare text without commit -- "
                            "creating synthetic narrative artifact: %s...",
                            iteration + 1,
                            bare[:200],
                        )
                        synthetic_artifact = {
                            "kind": ARTIFACT_KIND_NARRATIVE,
                            "payload": bare,
                            "audience": "self",
                            "target_player_ids": [],
                            "location_id": None,
                            "exclude_player_ids": [],
                        }
                        ctx["artifacts"].append(synthetic_artifact)
                        await self._deliver_artifacts(ctx, [synthetic_artifact], [])
                    elif response_msg.content:
                        logger.debug(f"Architect [{iteration+1}] finished with text (not sent): "
                                     f"{response_msg.content[:200]}...")
                    logger.info(f"Architect completed after {iteration + 1} iterations")
                    break

                if response_msg.content:
                    logger.debug(f"Architect [{iteration+1}] thinking: {response_msg.content[:300]}...")

                messages.append(self._msg_to_dict(response_msg))

                for tool_call in response_msg.tool_calls:
                    tool_name = tool_call.function.name
                    tool_args_raw = tool_call.function.arguments
                    args_preview = tool_args_raw[:500] if len(tool_args_raw) > 500 else tool_args_raw
                    logger.info(f"Architect [{iteration+1}] tool call: {tool_name}({args_preview})")

                    result = await self._dispatch_tool(tool_call, ctx)

                    def _safe_default(obj):
                        if hasattr(obj, 'model_dump'):
                            return obj.model_dump()
                        return str(obj)
                    result_str = json.dumps(result, ensure_ascii=False, default=_safe_default)
                    result_preview = result_str[:500] if len(result_str) > 500 else result_str
                    logger.info(f"Architect [{iteration+1}] tool result ({tool_name}): {result_preview}")

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result_str
                    })

                # T1B: Early exit – if commit was the only tool call and it
                # succeeded, the LLM's next turn would almost always just say
                # "done".  Skip that round-trip for common task profiles.
                # Check the last tool result for each call to detect errors.
                tool_results_ok = all(
                    not isinstance(r, dict) or "error" not in r
                    for r in [
                        json.loads(m["content"]) if isinstance(m.get("content"), str) else {}
                        for m in messages[-len(response_msg.tool_calls):]
                        if m.get("role") == "tool"
                    ]
                )
                tool_names = [tc.function.name for tc in response_msg.tool_calls]
                had_commit = ("commit_world_event" in tool_names or "commit" in tool_names) and tool_results_ok
                had_present_form = "present_form" in tool_names and tool_results_ok
                only_terminal_tools = all(
                    n in (
                        "commit_world_event",
                        "commit",
                        "present_form",
                        "return_structured_result",
                        "roll_dice",
                        "read_node",
                        "queue_materialization",
                    )
                    for n in tool_names
                )
                if had_commit and only_terminal_tools and task_profile in (
                    TASK_PROFILE_WORLD_ACTION,
                    TASK_PROFILE_PERCEPTION_RENDER,
                    TASK_PROFILE_WORKFLOW,
                    TASK_PROFILE_BACKGROUND_SIMULATION,
                ):
                    logger.info(
                        "Architect completed after %d iterations (early exit after commit)",
                        iteration + 1,
                    )
                    break
                if had_present_form and only_terminal_tools and task_profile in (
                    TASK_PROFILE_WORLD_ACTION,
                    TASK_PROFILE_WORKFLOW,
                ):
                    logger.info(
                        "Architect completed after %d iterations (early exit after present_form)",
                        iteration + 1,
                    )
                    break
            except (KeyError, ValueError, TypeError) as e:
                logger.warning(f"Architect tool error at iteration {iteration}: {e}", exc_info=True)
                if not ctx["displayed_messages"]:
                    error_artifact = {
                        "kind": ARTIFACT_KIND_NARRATIVE,
                        "payload": "Something went wrong while processing your request.",
                        "summary": "architect_tool_error",
                        "audience": "self",
                        "target_player_ids": [],
                        "location_id": None,
                        "exclude_player_ids": [],
                    }
                    ctx["artifacts"].append(error_artifact)
                    await self._deliver_artifacts(ctx, [error_artifact], [])
                break
            except Exception as e:
                logger.error(f"Unexpected architect error at iteration {iteration}: {e}", exc_info=True)
                if not ctx["displayed_messages"]:
                    error_artifact = {
                        "kind": ARTIFACT_KIND_NARRATIVE,
                        "payload": "Something went wrong while processing your request.",
                        "summary": "architect_unexpected_error",
                        "audience": "self",
                        "target_player_ids": [],
                        "location_id": None,
                        "exclude_player_ids": [],
                    }
                    ctx["artifacts"].append(error_artifact)
                    await self._deliver_artifacts(ctx, [error_artifact], [])
                break
        else:
            logger.warning(f"Architect reached max iterations ({max_iterations})")

    @staticmethod
    def _msg_to_dict(msg) -> dict:
        """Convert a ChatCompletionMessage or SimpleNamespace to a plain dict
        that the OpenAI SDK can serialise on subsequent API calls."""
        if hasattr(msg, 'model_dump') and not isinstance(msg, SimpleNamespace):
            return msg.model_dump()
        d: dict = {
            "role": getattr(msg, 'role', 'assistant'),
            "content": getattr(msg, 'content', None),
        }
        tool_calls = getattr(msg, 'tool_calls', None)
        if tool_calls:
            d["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": Architect._sanitize_tool_arguments_json(tc.function.arguments),
                    },
                }
                for tc in tool_calls
            ]
        return d

    @staticmethod
    def _repair_json(raw: str) -> str:
        """Attempt to repair truncated JSON from LLM output (e.g., missing closing braces)."""
        # Count unbalanced braces/brackets (ignoring those inside strings)
        in_string = False
        escape = False
        open_braces = 0
        open_brackets = 0
        for ch in raw:
            if escape:
                escape = False
                continue
            if ch == '\\' and in_string:
                escape = True
                continue
            if ch == '"' and not escape:
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == '{':
                open_braces += 1
            elif ch == '}':
                open_braces -= 1
            elif ch == '[':
                open_brackets += 1
            elif ch == ']':
                open_brackets -= 1

        # Append missing closers
        repair = ']' * max(0, open_brackets) + '}' * max(0, open_braces)
        if repair:
            return raw + repair
        return raw

    @staticmethod
    def _sanitize_tool_arguments_json(raw: Optional[str]) -> str:
        """Ensure tool-call arguments stored in message history are valid JSON.

        Some providers return tool-call arguments with truncated trailing braces.
        We already repair that form for local tool dispatch, but if we store the
        original malformed string back into `messages`, providers like DashScope
        reject the next round with a 400 because `function.arguments` must itself
        be valid JSON. Normalize it here before re-sending assistant tool calls.
        """
        text = raw or ""
        if not text.strip():
            return "{}"
        try:
            json.loads(text)
            return text
        except json.JSONDecodeError:
            repaired = Architect._repair_json(text)
            try:
                json.loads(repaired)
                return repaired
            except json.JSONDecodeError:
                logger.warning("Architect: unable to sanitize malformed tool-call arguments; replacing with empty object")
                return "{}"

    async def _dispatch_tool(self, tool_call, ctx: Dict[str, Any]) -> Any:
        """Dispatch a tool call to the appropriate handler."""
        name = tool_call.function.name
        raw_arguments = tool_call.function.arguments or ""
        if not raw_arguments.strip():
            args = {}
        else:
            try:
                args = json.loads(raw_arguments)
            except json.JSONDecodeError:
                # Attempt JSON repair (LLM sometimes drops closing braces when text contains { })
                try:
                    repaired = self._repair_json(raw_arguments)
                    args = json.loads(repaired)
                    logger.info(f"Architect: repaired malformed JSON for '{name}' (added missing closers)")
                except json.JSONDecodeError:
                    logger.warning(f"Architect: failed to parse tool args for '{name}': {tool_call.function.arguments}")
                    return {"error": f"Invalid JSON arguments for tool '{name}'"}

        handler = self._tool_registry.get(name)
        if not handler:
            logger.warning(f"Architect: unknown tool '{name}'")
            return {"error": f"Unknown tool '{name}'"}

        try:
            result = await handler(args, ctx)
            logger.debug(f"Architect tool '{name}' returned: {str(result)[:200]}")
            return result
        except Exception as e:
            logger.error(f"Architect tool '{name}' failed: {e}", exc_info=True)
            return {"error": f"Tool '{name}' failed: {str(e)}"}

    # ═══════════════════════════════════════════════════════════════════════════
    # Prompt Building
    # ═══════════════════════════════════════════════════════════════════════════









    # ═══════════════════════════════════════════════════════════════════════════
    # Core Tool Implementations
    # ═══════════════════════════════════════════════════════════════════════════









    # ═══════════════════════════════════════════════════════════════════════════
    # World Event Tool
    # ═══════════════════════════════════════════════════════════════════════════








    # ═══════════════════════════════════════════════════════════════════════════
    # Helper Methods
    # ═══════════════════════════════════════════════════════════════════════════











            # Do not re-render perception here.  This method is called after
            # background materialization and timed events to push updated
            # game_state (objects, characters, etc.).  The player already has
            # the scene text from a prior narration or explicit perception
            # request; triggering a full Architect render_perception call
            # would be expensive and redundant.
