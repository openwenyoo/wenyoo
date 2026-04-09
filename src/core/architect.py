"""
Architect Agent - Unified LLM agent for the AI Native game engine.

The Architect is a single LLM agent that replaces all scattered LLM call sites.
It operates inside a tool-calling loop with two categories of tools:

- Read Tools (agentic search) -- query game state to gather context
- Write Tools (effects/actions) -- act on the world, including sending text to the player

Key insight: the Architect calls `commit_world_event` as a tool mid-loop, atomically
narrating to the player AND applying state changes in a single call.
"""

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.game_kernel import GameKernel
    from src.models.game_state import GameState
    from src.models.story_models import Story, Effect, StoryNode, StoryObject, Character

logger = logging.getLogger(__name__)

TASK_PROFILE_WORLD_ACTION = "worldAction"
TASK_PROFILE_PERCEPTION_RENDER = "perceptionRender"
TASK_PROFILE_UI_DECISION = "uiDecision"
TASK_PROFILE_WORKFLOW = "workflowTask"
TASK_PROFILE_BACKGROUND_SIMULATION = "backgroundSimulation"


# Artifact kinds (extensible)
ARTIFACT_KIND_NARRATIVE = "narrative"
ARTIFACT_KIND_STRUCTURED = "structured"

DEFAULT_TASK_PROFILE_BY_TYPE = {
    "player_input": TASK_PROFILE_WORLD_ACTION,
    "execute_intent": TASK_PROFILE_WORLD_ACTION,
    "guided_intent": TASK_PROFILE_WORLD_ACTION,
    "scene_interaction": TASK_PROFILE_WORLD_ACTION,
    "character_interaction": TASK_PROFILE_WORLD_ACTION,
    "tool_assisted_decision": TASK_PROFILE_WORLD_ACTION,
    "render_perception": TASK_PROFILE_PERCEPTION_RENDER,
    "process_form_result": TASK_PROFILE_WORKFLOW,
    "process_event": TASK_PROFILE_WORKFLOW,
    "background_materialization": TASK_PROFILE_BACKGROUND_SIMULATION,
    "ui_requested_generation": TASK_PROFILE_UI_DECISION,
}


def infer_task_profile(task_type: str, explicit_profile: Optional[str] = None) -> str:
    """Resolve the task profile that should govern Architect behavior."""
    if explicit_profile:
        return explicit_profile
    return DEFAULT_TASK_PROFILE_BY_TYPE.get(task_type, TASK_PROFILE_WORLD_ACTION)




# ═══════════════════════════════════════════════════════════════════════════════
# Task Dataclass
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ArchitectTask:
    """Describes what the Architect should do in a single invocation."""
    task_type: str                  # "player_input", "render_perception", "process_form_result", "process_event", "background_materialization"
    player_input: Optional[str] = None      # For player_input tasks
    node_id: Optional[str] = None           # For render_perception tasks
    event_context: Optional[str] = None     # For trigger/event tasks
    form_data: Optional[Dict[str, Any]] = None  # For process_form_result tasks
    task_profile: Optional[str] = None
    purpose: Optional[str] = None
    structured_input: Optional[Dict[str, Any]] = None
    extra_context: Dict[str, Any] = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════════════════
# Architect Agent
# ═══════════════════════════════════════════════════════════════════════════════

class Architect:
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
        """Fill task contract defaults so callers do not need frontend-shaped assumptions."""
        task.task_profile = infer_task_profile(task.task_type, task.task_profile)
        return task

    # ═══════════════════════════════════════════════════════════════════════════
    # Tool Registration
    # ═══════════════════════════════════════════════════════════════════════════

    def _register_tools(self):
        """Register Architect tools for runtime narration and interaction."""

        # TODO(graph-context): Keep the public "local"/"full" interface stable for
        # the Architect, but reinterpret these views once graph-based context
        # retrieval exists. "local" should become a bounded relevant subgraph
        # around the active interaction, while "full" should become a broader
        # graph expansion rather than a naive whole-world dump.
        self._register("read_game_state", self._tool_read_game_state, {
            "type": "function",
            "function": {
                "name": "read_game_state",
                "description": (
                    "Returns the current game state as a JSON object. "
                    "Use view='local' for a smaller snapshot focused on the current "
                    "scene and player, or view='full' for broader world context. "
                    "Contains: variables (including players), character_states "
                    "(per character with name/definition/state/properties), "
                    "object_states (per object with name/definition/state/properties), "
                    "nodes (with actions, objects, triggers, hints, groups, state), "
                    "visited_nodes, version, message_history."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "view": {
                            "type": "string",
                            "enum": ["local", "full"],
                            "description": "local = current scene and player focused snapshot, full = broader world state."
                        },
                        "max_history": {
                            "type": "integer",
                            "description": "Maximum number of recent messages to include in message_history."
                        }
                    },
                    "required": []
                }
            }
        })

        # Legacy aliases: handler-only, not exposed to LLM via tool definitions.
        # If the LLM somehow calls these names, the dispatch still works.
        self._tool_registry["commit_world_event"] = self._tool_commit_world_event
        self._tool_registry["return_structured_result"] = self._tool_return_structured_result

        self._register("roll_dice", self._tool_roll_dice, {
            "type": "function",
            "function": {
                "name": "roll_dice",
                "description": "Roll dice using standard notation. Use for skill checks, random outcomes, etc.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "dice": {"type": "string", "description": "Dice notation like '1d20', '2d6+5', '1d100'"},
                        "reason": {"type": "string", "description": "Why this roll is being made (for logging)"}
                    },
                    "required": ["dice"]
                }
            }
        })

        # TODO: Once the graph feature provides linked/adjacent node info in
        # the pre-injected state, this tool may become unnecessary for most
        # transitions. Evaluate removal at that point.
        self._register("read_node", self._tool_read_node, {
            "type": "function",
            "function": {
                "name": "read_node",
                "description": (
                    "Read full details for a specific node by ID. Returns definition, "
                    "state, actions, triggers, hints, objects, and characters "
                    "at that location. Use this when you need to transition to a node "
                    "whose full details are not in the pre-loaded state (i.e. nodes "
                    "that only show {id, name} in read_game_state)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "node_id": {
                            "type": "string",
                            "description": "The node ID to read"
                        }
                    },
                    "required": ["node_id"]
                }
            }
        })

        self._register("queue_materialization", self._tool_queue_materialization, {
            "type": "function",
            "function": {
                "name": "queue_materialization",
                "description": (
                    "Create lightweight interactive stubs for newly introduced "
                    "characters, objects, or actions. Use this when a node or "
                    "story rule explicitly asks you to materialize ambient "
                    "entities before or alongside narration."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "entities": {
                            "type": "array",
                            "description": "Entities to create immediately.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "entity_type": {
                                        "type": "string",
                                        "enum": ["character", "object", "action"],
                                        "description": "Type of entity to materialize."
                                    },
                                    "entity_data": {
                                        "type": "object",
                                        "description": (
                                            "Entity payload. For characters use id, name, "
                                            "definition, brief, and optional location. For "
                                            "objects use id, name, definition, brief, and "
                                            "location or 'inventory'. For actions use id and "
                                            "text/name."
                                        )
                                    }
                                },
                                "required": ["entity_type", "entity_data"]
                            }
                        }
                    },
                    "required": ["entities"]
                }
            }
        })

        self._register("present_form", self._tool_present_form, {
            "type": "function",
            "function": {
                "name": "present_form",
                "description": (
                    "Present a story-defined form to the acting player and pause "
                    "normal input until they submit it. Use this when a clicked "
                    "option or story rule requires structured input such as class "
                    "selection, character creation, or a questionnaire."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "form_id": {
                            "type": "string",
                            "description": "The ID of the form defined in story.forms."
                        },
                        "prefill": {
                            "type": "object",
                            "description": "Optional prefilled field values."
                        },
                    },
                    "required": ["form_id"]
                }
            }
        })

        self._register("commit", self._tool_commit, {
            "type": "function",
            "function": {
                "name": "commit",
                "description": (
                    "Record a world event: apply authoritative state changes and "
                    "emit typed artifacts in one atomic call. Each artifact has a "
                    "'kind' and a 'payload'. Use kind 'narrative' for player-facing "
                    "text (with optional audience targeting) and kind 'structured' "
                    "for non-player-facing data returned to the caller/UI."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "artifacts": {
                            "type": "array",
                            "description": "Typed output artifacts produced by this commit.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "kind": {
                                        "type": "string",
                                        "enum": ["narrative", "structured"],
                                        "description": "Artifact kind."
                                    },
                                    "payload": {
                                        "description": (
                                            "Kind-dependent payload. For 'narrative': "
                                            "a player-facing text string (markdown supported). "
                                            "For 'structured': a JSON object for the caller/UI."
                                        )
                                    },
                                    "audience": {
                                        "type": "string",
                                        "enum": [
                                            "self", "players_here",
                                            "location_players", "session",
                                            "specific_players",
                                        ],
                                        "description": (
                                            "Who receives this artifact. Only meaningful for "
                                            "'narrative' kind. Defaults to 'players_here'."
                                        ),
                                        "default": "players_here"
                                    },
                                    "target_player_ids": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": (
                                            "Concrete player IDs when audience is "
                                            "'specific_players'."
                                        )
                                    },
                                    "location_id": {
                                        "type": "string",
                                        "description": (
                                            "Optional node/location ID for location-scoped "
                                            "delivery."
                                        )
                                    },
                                    "exclude_player_ids": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": (
                                            "Optional player IDs to exclude from the "
                                            "resolved audience."
                                        )
                                    },
                                    "summary": {
                                        "type": "string",
                                        "description": (
                                            "Optional short internal summary. Useful for "
                                            "'structured' artifacts."
                                        )
                                    }
                                },
                                "required": ["kind", "payload"]
                            }
                        },
                        "state_changes": {
                            "type": "object",
                            "description": (
                                "JSON merge-patch applied to game state. Only include "
                                "fields you want to change. Arrays are replaced not "
                                "appended — always write the full array. Omit this "
                                "field entirely when there are no mechanical state "
                                "changes."
                            )
                        },
                    },
                    "required": []
                }
            }
        })

    def _register(self, name: str, handler: Callable, definition: Dict):
        """Register a tool with its handler and OpenAI function definition."""
        self._tool_registry[name] = handler
        self._tool_definitions.append(definition)

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
        task_type = ctx.get("task_type", "")
        task_profile = ctx.get("task_profile", TASK_PROFILE_WORLD_ACTION)
        if task_profile in (
            TASK_PROFILE_WORLD_ACTION,
            TASK_PROFILE_PERCEPTION_RENDER,
            TASK_PROFILE_UI_DECISION,
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
                had_structured_result = "return_structured_result" in tool_names and tool_results_ok
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
                if (had_structured_result or had_commit) and only_terminal_tools and task_profile == TASK_PROFILE_UI_DECISION:
                    logger.info(
                        "Architect completed after %d iterations (early exit after structured result)",
                        iteration + 1,
                    )
                    break

            except (KeyError, ValueError, TypeError) as e:
                logger.warning(f"Architect tool error at iteration {iteration}: {e}", exc_info=True)
                if not ctx["displayed_messages"]:
                    error_artifact = {
                        "kind": ARTIFACT_KIND_STRUCTURED if task_profile == TASK_PROFILE_UI_DECISION else ARTIFACT_KIND_NARRATIVE,
                        "payload": (
                            {"error": "Something went wrong while processing your request."}
                            if task_profile == TASK_PROFILE_UI_DECISION
                            else "Something went wrong while processing your request."
                        ),
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
                        "kind": ARTIFACT_KIND_STRUCTURED if task_profile == TASK_PROFILE_UI_DECISION else ARTIFACT_KIND_NARRATIVE,
                        "payload": (
                            {"error": "Something went wrong while processing your request."}
                            if task_profile == TASK_PROFILE_UI_DECISION
                            else "Something went wrong while processing your request."
                        ),
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
                        "arguments": tc.function.arguments,
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

    def _get_system_prompt(self) -> str:
        """Load the Architect system prompt from file."""
        if self._system_prompt is None:
            prompt_path = os.path.join("prompts", "architect_system.txt")
            try:
                with open(prompt_path, "r", encoding="utf-8") as f:
                    self._system_prompt = f.read()
            except FileNotFoundError:
                logger.warning(f"Architect system prompt not found: {prompt_path}")
                self._system_prompt = self._get_fallback_system_prompt()
        return self._system_prompt

    def _get_fallback_system_prompt(self) -> str:
        """Minimal fallback system prompt if file is missing."""
        return (
            "You are the Architect, the world-builder for an AI native text based game engine. "
            "You manage all narrative content and world state changes using "
            "read_game_state, commit_world_event, roll_dice, read_node, and "
            "queue_materialization. "
            "Use commit_world_event to narrate AND record state changes atomically."
        )

    def _build_world_index(self, game_state: 'GameState', player_id: str,
                            story: 'Story') -> str:
        """
        Build a mostly-static story manifest for the initial prompt prefix.

        Keep volatile runtime state out of this section so provider-side prefix
        caching can reuse it more often across consecutive turns.
        """
        lines = []
        lines.append("## STORY MANIFEST")

        if story.genre:
            lines.append(f"GENRE: {story.genre}")

        node_parts = []
        for nid, node in game_state.nodes.items():
            node_name = node.name or nid
            node_parts.append(f"{nid} ({node_name})")
        lines.append(f"NODES: {', '.join(node_parts)}")

        char_parts = []
        if story.characters:
            for char in story.characters:
                char_parts.append(f"{char.id} ({char.name})")
        lines.append(f"CHARACTERS: {', '.join(char_parts) if char_parts else '(none)'}")

        key_vars = {}
        for k, v in game_state.variables.items():
            if k in ('players', 'nodes') or k.startswith('_') or k.startswith('lore_'):
                continue
            if isinstance(v, (str, int, float, bool)):
                key_vars[k] = v
        if key_vars:
            var_parts = [f"{k}={v}" for k, v in list(key_vars.items())[:20]]
            lines.append(f"KEY VARIABLES: {', '.join(var_parts)}")

        if story.metadata:
            lines.append(f"METADATA KEYS: {', '.join(story.metadata.keys())}")

        return "\n".join(lines)

    def _build_recent_conversation_lines(
        self,
        game_state: 'GameState',
        player_id: str,
        controlled_char_id: Optional[str],
        limit: int = 3,
    ) -> List[str]:
        recent = game_state.get_recent_messages(
            limit,
            player_id=player_id,
            character_id=controlled_char_id,
        )
        if not recent:
            return []

        lines = ["## RECENT CONVERSATION"]
        for msg in recent:
            role = msg.get("role", "?")
            speaker = msg.get("speaker", "")
            content_text = msg.get("content", "")[:240]
            label = speaker or role
            lines.append(f"  [{label}]: {content_text}")
        lines.append("")
        return lines

    def _build_group_reference_lines(
        self,
        node,
        game_state: 'GameState',
    ) -> List[str]:
        if not node:
            return []

        group_ids = [
            group_id.strip()
            for group_id in getattr(node, 'groups', []) or []
            if isinstance(group_id, str) and group_id.strip()
        ]
        if not group_ids:
            return []

        variables = getattr(game_state, 'variables', {}) or {}
        lines: List[str] = ["## RELEVANT GROUP REFERENCES"]
        seen = set()
        for group_id in group_ids:
            if group_id in seen:
                continue
            seen.add(group_id)
            group_key = group_id if group_id.startswith('group_') else f'group_{group_id}'
            group_text = variables.get(group_key)
            if not isinstance(group_text, str) or not group_text.strip():
                continue
            label = group_id.replace('_', ' ').title()
            lines.append(f"### {label} ({group_key})")
            lines.append(group_text.strip())
            lines.append("")

        if len(lines) == 1:
            return []
        return lines

    def _build_visible_object_lines(
        self,
        node,
        game_state: 'GameState',
    ) -> List[str]:
        if not node:
            return []

        lines: List[str] = []
        visible_objs = [
            o for o in node.objects
            if game_state.is_object_visible(o)
        ]
        for obj in visible_objs:
            obj_state = game_state.object_states.get(obj.id, {})
            definition = obj_state.get('definition', obj.definition) or ""
            interactions = re.findall(r'##\s*(.+)', definition) if definition else []
            interaction_str = ", ".join(interactions) if interactions else ""

            state_text = obj_state.get('state', obj.state) or ""

            header = f"  - {obj.id} ({obj.name})"
            if interaction_str:
                header += f"  [interactions: {interaction_str}]"
            lines.append(header)
            if state_text:
                lines.append(f"    state: {state_text.strip()}")
        return lines

    def _build_available_action_lines(
        self,
        node,
        game_state: 'GameState',
        player_id: str,
    ) -> List[str]:
        if not node or not node.actions:
            return []

        lines: List[str] = []
        for action in node.actions:
            is_avail, _ = action.is_available(game_state, player_id)
            if not is_avail:
                continue
            effect_notes = []
            for effect in action.effects or []:
                if getattr(effect, "type", None) == "present_form" and getattr(effect, "form_id", None):
                    effect_notes.append(f"present_form({effect.form_id})")
            suffix = f" [{', '.join(effect_notes)}]" if effect_notes else ""
            lines.append(f"  - {action.id}: {action.text or action.description or action.id}{suffix}")
        return lines

    def _build_client_context_lines(
        self,
        task: ArchitectTask,
        game_state: 'GameState',
    ) -> List[str]:
        """Build optional client-context guidance for custom frontend tasks."""
        story = getattr(game_state, "story", None)
        frontend = getattr(story, "frontend", None) if story else None
        client_context = getattr(frontend, "client_context", None) if frontend else None
        if not client_context:
            return []

        lines: List[str] = ["## CLIENT CONTEXT"]
        representation = getattr(client_context, "representation", None) or "custom_ui"
        description = getattr(client_context, "description", None)
        lines.append(f"Representation: {representation}")
        if description:
            lines.append(f"Representation details: {description}")

        active_view = str(task.extra_context.get("active_view") or "").strip()
        view_context = None
        if active_view and getattr(client_context, "views", None):
            view_context = client_context.views.get(active_view)
        if active_view:
            lines.append(f"Active view: {active_view}")

        if view_context:
            if view_context.description:
                lines.append(f"View details: {view_context.description}")
            if view_context.player_sees:
                lines.append(f"Player sees: {view_context.player_sees}")
            if view_context.player_can:
                lines.append(f"Player can: {view_context.player_can}")
            guidance = view_context.artifact_guidance or client_context.default_guidance
        else:
            guidance = client_context.default_guidance

        if guidance:
            lines.append(f"Guidance: {guidance}")
        lines.append("")
        return lines

    def _build_task_prompt(self, task: ArchitectTask, world_index: str,
                            game_state: 'GameState', player_id: str) -> str:
        """Build the user message for a specific task."""
        parts = []

        # Inject all lore_* variables as a LOREBOOK section
        lore_parts = []
        for k, v in game_state.variables.items():
            if k.startswith('lore_') and isinstance(v, str) and v.strip():
                label = k.replace('lore_', '').replace('_', ' ').title()
                lore_parts.append(f"### {label}\n{v.strip()}")
        if lore_parts:
            parts.append("## LOREBOOK\n" + "\n\n".join(lore_parts))
            parts.append("")

        parts.append(world_index)
        parts.append("")
        parts.append("## TASK CONTRACT")
        parts.append(f"Task type: {task.task_type}")
        parts.append(f"Task profile: {task.task_profile or infer_task_profile(task.task_type)}")
        if task.purpose:
            parts.append(f"Purpose: {task.purpose}")
        parts.append("")
        parts.extend(self._build_client_context_lines(task, game_state))

        if task.task_type in (
            "player_input",
            "execute_intent",
            "guided_intent",
            "scene_interaction",
            "character_interaction",
            "tool_assisted_decision",
            "ui_requested_generation",
        ):
            player_location = game_state.get_player_location(player_id)
            node = game_state.nodes.get(player_location) if player_location else None
            controlled_char_id = game_state.get_controlled_character_id(player_id)
            controlled_char = (
                game_state.story.get_character(controlled_char_id)
                if controlled_char_id and game_state.story
                else None
            )

            group_reference_lines = self._build_group_reference_lines(node, game_state)
            if group_reference_lines:
                parts.extend(group_reference_lines)

            parts.append("## TURN CONTEXT")
            parts.append(
                "A preloaded read_game_state(view='local') snapshot is already in the conversation. "
                "Use that local snapshot for current runtime truth. Call read_game_state(view='full') "
                "only if you need broader world context beyond the current scene."
            )
            if node:
                parts.append(f"Current node: {player_location} ({node.name or player_location})")
            else:
                parts.append(f"Current node: {player_location or '(unknown)'}")

            inventory = game_state.get_player_inventory(player_id)
            inv_names = []
            for item_id in inventory:
                item_obj = game_state.resolve_inventory_object(item_id)
                inv_names.append(item_obj.name if item_obj else item_id)

            parts.append("## PLAYER STATE")
            parts.append(f"Player ID: {player_id}")
            parts.append(f"Controlled character: {controlled_char_id or '(none)'}")
            parts.append(f"Location: {player_location}")
            parts.append(f"Inventory: {inv_names if inv_names else '(empty)'}")
            if controlled_char_id:
                char_state = game_state.character_states.get(controlled_char_id, {})
                if controlled_char and controlled_char.name:
                    parts.append(f"Character name: {controlled_char.name}")
                char_state_text = char_state.get('state') or (
                    controlled_char.state if controlled_char else ""
                )
                if char_state_text:
                    parts.append(f"Character State: {char_state_text}")
                char_status = char_state.get('properties', {}).get('status', [])
                if char_status:
                    parts.append(f"Status: {char_status}")
                char_stats = char_state.get('properties', {}).get('stats', {})
                if char_stats:
                    parts.append(f"Stats: {char_stats}")
                char_memory = char_state.get('memory', [])[-3:]
                if char_memory:
                    parts.append(f"Recent character memory: {char_memory}")
            parts.append("")

            if node:
                char_here_lines = []
                for char_id in self._get_nonplayable_characters_at_node(game_state, player_location):
                    char_def = game_state.story.get_character(char_id) if game_state.story else None
                    if not char_def:
                        continue
                    char_state = game_state.character_states.get(char_id, {})
                    dep = char_state.get('state', char_def.state) or ""
                    mem = char_state.get('memory', list(char_def.memory)) if char_state else list(char_def.memory)
                    status = char_state.get('properties', dict(char_def.properties)).get('status', [])
                    char_here_lines.append(f"  - {char_id} ({char_def.name})")
                    if dep:
                        char_here_lines.append(f"    state: {dep}")
                    if status:
                        char_here_lines.append(f"    status: {status}")
                    if mem:
                        char_here_lines.append(f"    recent memory: {mem[-2:]}")
                if char_here_lines:
                    parts.append("## CHARACTERS HERE")
                    parts.extend(char_here_lines)
                    parts.append("")

            players_here = self._get_player_summaries_at_location(game_state, player_id, player_location)
            if players_here:
                parts.append("## PLAYERS HERE")
                for player_summary in players_here:
                    parts.append(self._format_player_summary_for_prompt(player_summary))
                parts.append("")

            session_players = self._get_session_player_summaries(game_state, player_id)
            if session_players:
                parts.append("## SESSION PLAYERS")
                for player_summary in session_players:
                    parts.append(self._format_player_summary_for_prompt(player_summary))
                parts.append("")

            parts.extend(
                self._build_recent_conversation_lines(
                    game_state,
                    player_id,
                    controlled_char_id,
                    limit=3,
                )
            )

            input_type = task.extra_context.get("input_type", "typed")
            action_hint = task.extra_context.get("action_hint", "")

            _INPUT_BOUNDARY = "════ UNTRUSTED PLAYER INPUT ════"
            _MAX_PLAYER_INPUT_LEN = 2000
            player_input = task.player_input or ""
            if len(player_input) > _MAX_PLAYER_INPUT_LEN:
                player_input = player_input[:_MAX_PLAYER_INPUT_LEN]
                logger.warning("Player input truncated from %d to %d chars",
                               len(task.player_input), _MAX_PLAYER_INPUT_LEN)

            if task.task_type == "player_input":
                parts.append("## PLAYER INPUT")
                parts.append(_INPUT_BOUNDARY)
                if input_type == "action_click":
                    parts.append(f'The player selected the option: "{player_input}"')
                else:
                    parts.append(f'The player says: "{player_input}"')
                parts.append(_INPUT_BOUNDARY)

                if action_hint:
                    parts.append("")
                    parts.append(f"**Action hint (from story author):** {action_hint}")
            else:
                parts.append("## PURPOSE-DRIVEN TASK")
                parts.append(f"Task type: {task.task_type}")
                if task.purpose:
                    parts.append(f"Purpose: {task.purpose}")
                if player_input:
                    parts.append(_INPUT_BOUNDARY)
                    parts.append(f'Player-facing input or wording: "{player_input}"')
                    parts.append(_INPUT_BOUNDARY)
                if task.structured_input:
                    parts.append("Structured input:")
                    parts.append(json.dumps(task.structured_input, ensure_ascii=False, indent=2))
                if action_hint:
                    parts.append(f"Author/UI hint: {action_hint}")

            parts.append("")
            parts.append(
                "## RULE RESOLUTION GUIDE\n"
                "Resolve the player's action using the hierarchy (highest priority first):\n"
                "1. ENTITY RULES: Check definitions of targeted entities\n"
                "2. NODE RULES: Check current node details from the preloaded local state or read_node\n"
                "3. GROUP REFERENCES: Check any RELEVANT GROUP REFERENCES injected for this node\n"
                "4. WORLD RULES: Check LOREBOOK for story-wide rules\n"
                "5. GENRE: Reason from the story's genre and world logic\n"
                "6. GENERAL INTELLIGENCE: Improvise within genre constraints\n"
                "Higher-layer rules override lower ones ONLY for the specific "
                "aspects they address."
            )
            parts.append("")
            if task.task_type == "player_input":
                parts.append(
                    "Respond to the player's input. Only interact with what the "
                    "player asked about. Use read_node(node_id) for full details on a "
                    "specific location or read_game_state(view='full') if you need "
                    "broader world context. Use commit_world_event() for all state "
                    "changes. If the selected action should open a story-defined form, "
                    "call present_form(form_id) and stop instead of narrating the "
                    "selection as ordinary text."
                )
            else:
                parts.append(
                    "Resolve this purpose-driven task from the supplied context. "
                    "Treat the UI and author-provided context as request framing, not "
                    "as authoritative world truth. Use the current world state and tools "
                    "to decide what actually happens. Use commit_world_event() for all "
                    "player-visible or consequential outcomes. If the task should collect "
                    "structured input before continuing, call present_form(form_id) and stop."
                )

            parts.append("")
            if task.task_profile == TASK_PROFILE_UI_DECISION:
                parts.append(
                    "## PROFILE RULES: UI DECISION\n"
                    "This task is for non-player-facing structured reasoning.\n"
                    "- Do not narrate to players by default.\n"
                    "- Do not call commit_world_event unless the task truly decides a real world event.\n"
                    "- If you are returning a UI judgment, recommendation, ranking, or schema, call return_structured_result(result=...).\n"
                    "- Keep the result grounded in authoritative state and authored rules."
                )
            else:
                parts.append(
                    "## PROFILE RULES: WORLD ACTION\n"
                    "This task resolves real in-world action. If it causes a player-facing or consequential outcome, "
                    "use commit_world_event(). If structured input is required first, use present_form(form_id)."
                )

            action_lines = self._build_available_action_lines(node, game_state, player_id)
            if action_lines:
                parts.append("\n## AVAILABLE ACTIONS (reference only)")
                parts.extend(action_lines)

            object_lines = self._build_visible_object_lines(node, game_state)
            if object_lines:
                parts.append("\n## OBJECTS AT CURRENT NODE")
                parts.extend(object_lines)

        elif task.task_type == "render_perception":
            node_id = task.node_id or game_state.get_player_location(player_id)
            node = game_state.nodes.get(node_id) if node_id else None
            controlled_char_id = game_state.get_controlled_character_id(player_id)
            controlled_char = (
                game_state.story.get_character(controlled_char_id)
                if controlled_char_id and game_state.story
                else None
            )

            if node and node_id:
                parts.append("## RENDER PERCEPTION")
                parts.append(f"Render the current scene perception for node: {node_id} ({node.name or node_id})")
                parts.append(
                    "A preloaded read_game_state(view='local') snapshot is already in the conversation. "
                    "Use read_node(node_id) or read_game_state(view='full') only if you need more than the local scene."
                )
                parts.append("")

                if controlled_char_id:
                    parts.append("## VIEW CHARACTER")
                    parts.append(f"Controlled character: {controlled_char_id}")
                    if controlled_char and controlled_char.name:
                        parts.append(f"Name: {controlled_char.name}")
                    char_state = game_state.character_states.get(controlled_char_id, {})
                    char_state_text = char_state.get("state") or (
                        controlled_char.state if controlled_char else ""
                    )
                    if char_state_text:
                        parts.append(f"State: {char_state_text}")
                    char_status = char_state.get("properties", {}).get("status", [])
                    if char_status:
                        parts.append(f"Status: {char_status}")
                    parts.append("")

                visible_objs = self._build_visible_object_lines(node, game_state)
                if visible_objs:
                    parts.append("## VISIBLE OBJECTS")
                    parts.extend(visible_objs)
                    parts.append("")

                char_lines = []
                for char_id in self._get_nonplayable_characters_at_node(game_state, node_id):
                    char_def = game_state.story.get_character(char_id) if game_state.story else None
                    if not char_def or char_def.is_playable:
                        continue
                    char_state = game_state.character_states.get(char_id, {})
                    dep = char_state.get("state", char_def.state) or char_def.definition
                    char_lines.append(f"- {char_id} ({char_def.name}): {dep}")
                if char_lines:
                    parts.append("## CHARACTERS HERE")
                    parts.extend(char_lines)
                    parts.append("")

                action_lines = []
                if node.actions:
                    for action in node.actions:
                        is_avail, _ = action.is_available(game_state, player_id)
                        if is_avail:
                            action_lines.append(
                                f"- {action.text or action.description or action.id}"
                            )
                if action_lines:
                    parts.append("## AVAILABLE ACTIONS")
                    parts.extend(action_lines)
                    parts.append("")

                parts.append(
                    "Generate fresh player-facing perception from the current world state for this controlled character.\n"
                    "This is a refresh/re-read, not a first arrival unless the state explicitly implies that.\n"
                    "Do NOT store the generated scene text back into node state as authoritative truth.\n"
                    "If the current world state implies consequential missing entities or links that must now exist, "
                    "include those creations in the same commit_world_event state_changes patch.\n"
                    "Call commit_world_event ONCE with the rendered perception. "
                    "Use state_changes only if the world itself must change to stay consistent with the narrative."
                )
                parts.append("")
                parts.append(
                    "This task profile is perceptionRender. The upper layer will capture and deliver the perception separately "
                    "from authoritative game_state sync."
                )

        elif task.task_type == "background_materialization":
            reason = task.extra_context.get("background_materialization_reason", "scene_enrichment")
            source_node_id = task.extra_context.get("background_source_node_id") or task.node_id
            visible_node_id = task.extra_context.get("background_visible_node_id") or source_node_id
            node = game_state.nodes.get(source_node_id) if source_node_id else None
            budget = task.extra_context.get("background_budget") or {}
            applied_changes = task.extra_context.get("background_applied_changes") or []

            parts.append("## BACKGROUND MATERIALIZATION")
            parts.append(
                "This is a deferred world-simulation follow-up after a prior authoritative commit. "
                "You are not repairing earlier prose. The earlier event is already true in state."
            )
            parts.append(f"Reason: {reason}")
            if source_node_id:
                parts.append(f"Source node: {source_node_id}")
            if visible_node_id and visible_node_id != source_node_id:
                parts.append(f"Visible node: {visible_node_id}")
            if budget:
                parts.append(f"Budget: {json.dumps(budget, ensure_ascii=False)}")
            if applied_changes:
                parts.append("Recently applied changes:")
                for change in applied_changes[:20]:
                    parts.append(f"- {change}")
            parts.append("")
            parts.append(
                "Rules:\n"
                "- Prefer enriching existing stubs over creating replacement entities.\n"
                "- When enriching a stub, upgrade static definition metadata (such as name/definition and other identity fields) "
                "as well as runtime state (state, memory, properties).\n"
                "- Keep changes small, coherent, and stable.\n"
                "- Do not duplicate ambient entities already present.\n"
                "- Offscreen changes may update state but must not be auto-revealed to players.\n"
                "- Use commit_world_event with state_changes; omit player-facing narrative unless connected players should immediately perceive the result.\n"
                "- If there is nothing useful to enrich in this pass, return no text and make no tool call.\n"
                "- Never emit explanatory prose, internal reasoning, or status text for this task."
            )
            parts.append("")

            if node and source_node_id:
                parts.append("## SOURCE NODE")
                parts.append(f"ID: {source_node_id}")
                parts.append(f"Name: {node.name or source_node_id}")
                if node.definition:
                    parts.append(f"Definition:\n{node.definition}")
                if node.state:
                    parts.append(f"State:\n{node.state}")
                parts.append("")

                visible_objs = []
                for obj in node.objects:
                    if game_state.is_object_visible(obj):
                        obj_state = game_state.object_states.get(obj.id, {})
                        visible_objs.append(
                            f"- {obj.id} ({obj.name}): "
                            f"{obj_state.get('state', obj.state) or ''}"
                        )
                if visible_objs:
                    parts.append("## OBJECTS HERE")
                    parts.extend(visible_objs)
                    parts.append("")

                char_lines = []
                for char_id in self._get_nonplayable_characters_at_node(game_state, source_node_id):
                    char_def = game_state.story.get_character(char_id) if game_state.story else None
                    if not char_def or char_def.is_playable:
                        continue
                    char_state = game_state.character_states.get(char_id, {})
                    dep = char_state.get("state", char_def.state) or char_def.definition
                    char_lines.append(f"- {char_id} ({char_def.name}): {dep}")
                if char_lines:
                    parts.append("## CHARACTERS HERE")
                    parts.extend(char_lines)
                    parts.append("")

            if reason == "nearby_world_simulation":
                parts.append(
                    "Focus on nearby or offscreen world continuity in the current region. "
                    "Favor modest updates to existing entities, factions, or locations over spawning many new ones."
                )
            else:
                parts.append(
                    "Focus on local scene enrichment for the current node and its immediate interactables. "
                    "Favor follow-up materialization of stubs and ambient concretization that strengthens the living world."
                )

        elif task.task_type == "process_form_result":
            form_info = task.form_data or {}
            form_id = form_info.get("form_id", "unknown")
            form_title = form_info.get("form_title", "")
            submitted_data = form_info.get("submitted_data", {})
            on_submit_summary = form_info.get("on_submit_summary", "")
            controlled_char_id = game_state.get_controlled_character_id(player_id)

            player_location = game_state.get_player_location(player_id)
            node = game_state.nodes.get(player_location) if player_location else None
            if node:
                parts.append("## CURRENT NODE")
                parts.append(f"ID: {player_location}")
                parts.append(f"Name: {node.name or player_location}")
                if node.state:
                    resolved = self.game_kernel.text_processor.substitute_variables(
                        node.state, game_state, player_id
                    )
                    parts.append(f"State:\n{resolved}")
                parts.append("")
            if controlled_char_id:
                parts.append("## CURRENT EMBODIMENT")
                parts.append(f"Controlled character before processing: {controlled_char_id}")
                parts.append("")

            parts.append("## FORM SUBMISSION RESULT")
            parts.append(f"Form: {form_id}" + (f" ({form_title})" if form_title else ""))
            parts.append(f"Player's choices: {json.dumps(submitted_data, ensure_ascii=False)}")
            if on_submit_summary:
                parts.append(f"Writer's on_submit flow: {on_submit_summary}")
            parts.append("")
            parts.append(
                "The writer's on_submit flow is authoritative. Resolve any placeholders "
                "from the submitted choices and any variables the engine already stored "
                "before this task. If the writer flow changes embodiment "
                "or location, include those exact mechanical changes in one "
                "commit_world_event state_changes patch before narrating.\n"
                "- set_controlled_character(target=X): write "
                "variables.players.<player_id>.controlled_character_id = X\n"
                "- goto_node(target=Y): move the relevant embodied character by writing "
                "character_states.<char_id>.properties.location = Y and update "
                "visited_nodes when the player newly reaches that node\n"
                "Narrate from the resulting controlled character and resulting location. "
                "Call commit_world_event ONCE, then STOP."
            )
            parts.append("")
            parts.append(
                "This task profile is workflowTask. Treat the form flow as authoritative workflow framing, but keep world state and player-facing outcome coherent."
            )

        elif task.task_type == "process_event":
            parts.append("## EVENT")
            parts.append(task.event_context or "An event occurred.")
            parts.append("")
            parts.append(
                "This event already became due in engine time. Resolve it now as one "
                "authoritative world event. If timed-event context includes intended "
                "state changes, treat those mechanical targets as authoritative and "
                "apply them through commit_world_event(state_changes=...). Narrate the "
                "result only to players who can currently perceive it. If no players "
                "should receive text immediately, you may commit state_changes without "
                "narrative."
            )
            parts.append("")
            parts.append(
                "This task profile is workflowTask. It is an engine-driven workflow/event resolution task, not a free-form chat turn."
            )

        if task.extra_context:
            skip_keys = {
                "input_type",
                "action_hint",
                "capture_only",
                "background_materialization",
                "background_materialization_reason",
                "background_source_node_id",
                "background_visible_node_id",
                "background_local_only",
                "background_allow_player_facing_narrative",
                "background_base_version",
                "background_budget",
                "background_applied_changes",
                "suppress_background_materialization",
            }
            for key, value in task.extra_context.items():
                if key.startswith("_") or key in skip_keys:
                    continue
                parts.append(f"\n## {key.upper()}")
                parts.append(str(value))

        return "\n".join(parts)

    # ═══════════════════════════════════════════════════════════════════════════
    # Core Tool Implementations
    # ═══════════════════════════════════════════════════════════════════════════

    def _tool_read_game_state_sync(
        self,
        game_state: 'GameState',
        player_id: str,
        story: 'Story',
        *,
        view: str = "full",
        max_history: int = 10,
    ) -> Dict:
        """Build the read_game_state payload without needing ctx."""
        # TODO(graph-context): This helper currently delegates to serializer
        # heuristics keyed by "local"/"full". Keep the API shape, but route these
        # modes through compiled-graph retrieval when that system lands.
        result = game_state.to_architect_json(
            player_id,
            view=view,
            max_history=max_history,
            include_message_history=max_history > 0,
        )
        if story and story.metadata:
            result["metadata"] = self._make_serializable(story.metadata)
        return result

    async def _tool_read_game_state(self, args: Dict, ctx: Dict) -> Dict:
        """Return the full game state as a JSON object."""
        game_state: 'GameState' = ctx["game_state"]
        player_id = ctx["player_id"]
        story: 'Story' = ctx["story"]
        view = str(args.get("view") or "full").lower()
        if view not in {"local", "full"}:
            view = "full"
        max_history_raw = args.get("max_history", 10)
        try:
            max_history = max(0, min(int(max_history_raw), 20))
        except (TypeError, ValueError):
            max_history = 10
        return self._tool_read_game_state_sync(
            game_state,
            player_id,
            story,
            view=view,
            max_history=max_history,
        )

    async def _tool_read_node(self, args: Dict, ctx: Dict) -> Dict:
        """Return full details for a single node, plus characters at that location."""
        node_id = args.get("node_id", "")
        game_state: 'GameState' = ctx["game_state"]
        story: 'Story' = ctx["story"]

        node = game_state.nodes.get(node_id)
        if not node:
            return {"error": f"Node '{node_id}' not found"}

        actions_list = []
        if node.actions:
            for action in node.actions:
                a_entry: Dict[str, Any] = {
                    'id': action.id,
                    'text': action.text or action.description or action.id,
                }
                if action.intent:
                    a_entry['intent'] = action.intent
                actions_list.append(a_entry)

        triggers_list = []
        if node.triggers:
            for trigger in node.triggers:
                t_entry: Dict[str, Any] = {
                    'id': trigger.id,
                    'type': trigger.type,
                }
                if trigger.intent:
                    t_entry['intent'] = trigger.intent
                if trigger.conditions:
                    t_entry['conditions'] = [c.dict() for c in trigger.conditions]
                triggers_list.append(t_entry)

        object_ids = [obj.id for obj in node.objects]

        result: Dict[str, Any] = {
            'id': node_id,
            'name': node.name or node_id,
            'definition': node.definition,
            'state': node.state or '',
            'properties': dict(node.properties),
            'actions': actions_list,
            'objects': object_ids,
        }
        if triggers_list:
            result['triggers'] = triggers_list
        node_groups = getattr(node, "groups", None)
        if node_groups:
            result['groups'] = list(node_groups)
        node_hints = getattr(node, "hints", None)
        if node_hints:
            result['hints'] = node_hints

        # Include characters at this node
        npc_ids = self._get_nonplayable_characters_at_node(game_state, node_id)
        if npc_ids and story:
            chars_here: Dict[str, Any] = {}
            for char_id in npc_ids:
                char_def = story.get_character(char_id)
                if not char_def:
                    continue
                char_state = game_state.character_states.get(char_id, {})
                chars_here[char_id] = {
                    'name': char_def.name,
                    'definition': char_def.definition,
                    'state': char_state.get('state', char_def.state) or '',
                    'memory': list(char_state.get('memory', list(char_def.memory))),
                    'properties': char_state.get('properties', dict(char_def.properties)),
                }
            if chars_here:
                result['characters_here'] = chars_here

        logger.debug("Architect: read_node('%s') returned %d chars", node_id, len(str(result)))
        return result

    async def _tool_present_form(self, args: Dict, ctx: Dict) -> Dict:
        """Present a story form to the active player."""
        form_id = (args.get("form_id") or "").strip()
        if not form_id:
            return {"error": "present_form requires a non-empty form_id"}

        # TODO: If we want the Architect to reason more intelligently about form
        # structure itself, add a form-schema read/summarization path here so it
        # can inspect field types, options, validation, and conditional display
        # rules before deciding when or how to present a form.
        game_state: 'GameState' = ctx["game_state"]
        player_id = ctx["player_id"]
        story: 'Story' = ctx["story"]
        prefill = args.get("prefill")

        try:
            result = await self.game_kernel.present_form(
                form_id,
                game_state,
                player_id,
                story,
                prefill=prefill if isinstance(prefill, dict) else None,
            )
        except Exception as e:
            logger.error("present_form failed for '%s': %s", form_id, e, exc_info=True)
            return {"error": f"Failed to present form '{form_id}': {str(e)}"}

        if result.get("success"):
            ctx["presented_form"] = {"form_id": form_id}
        return result

    async def _tool_return_structured_result(self, args: Dict, ctx: Dict) -> Dict:
        """Legacy shim: convert return_structured_result args to commit() format."""
        result = args.get("result")
        if not isinstance(result, dict):
            return {"error": "return_structured_result requires result to be an object"}

        commit_args: Dict[str, Any] = {
            "artifacts": [{
                "kind": ARTIFACT_KIND_STRUCTURED,
                "payload": result,
                "summary": (args.get("summary") or "").strip(),
            }]
        }
        return await self._tool_commit(commit_args, ctx)

    def _make_serializable(self, obj: Any) -> Any:
        """Recursively convert non-JSON-serializable objects to plain dicts/strings."""
        if obj is None or isinstance(obj, (str, int, float, bool)):
            return obj
        if isinstance(obj, dict):
            return {k: self._make_serializable(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [self._make_serializable(item) for item in obj]
        if hasattr(obj, '__dict__'):
            return {k: self._make_serializable(v) for k, v in obj.__dict__.items()
                    if not k.startswith('_')}
        return str(obj)

    async def _apply_world_event_state_changes(
        self,
        state_changes: Any,
        ctx: Dict[str, Any],
    ) -> List[str]:
        """Apply authoritative state changes for a world event and return touched paths."""
        if not isinstance(state_changes, dict):
            return []

        player_id = ctx["player_id"]
        game_state: 'GameState' = ctx["game_state"]
        applied = game_state.apply_merge_patch(state_changes, player_id)

        if any("character_states" in a for a in applied):
            node_id = game_state.get_player_location(player_id)
            if node_id:
                try:
                    await self.game_kernel._push_characters_update(
                        game_state,
                        player_id,
                        node_id,
                    )
                except Exception as e:
                    logger.error(f"commit_world_event: failed to push characters update: {e}")

        return applied

    def _record_world_event(
        self,
        ctx: Dict[str, Any],
        *,
        deliveries: List[Dict[str, Any]],
        state_applied: List[str],
        target_player_ids: List[str],
        version: int,
    ) -> Dict[str, Any]:
        """Store the authoritative event result independently from client delivery."""
        event_record = {
            "task_type": ctx.get("task_type"),
            "task_profile": ctx.get("task_profile"),
            "deliveries": self._make_serializable(deliveries),
            "state_applied": list(state_applied),
            "target_player_ids": list(target_player_ids),
            "version": version,
        }
        ctx["world_events"].append(event_record)
        return event_record

    # ═══════════════════════════════════════════════════════════════════════════
    # World Event Tool
    # ═══════════════════════════════════════════════════════════════════════════

    async def _tool_commit(self, args: Dict, ctx: Dict) -> Dict:
        """Unified commit: apply state changes and record typed artifacts.

        This is the core commit primitive. It applies authoritative state
        mutations and records typed artifacts (narrative, structured, etc.)
        without making delivery decisions. Upper layers consume the artifacts
        list from ctx and handle delivery according to their own policies.
        """
        state_changes = args.get("state_changes")
        # LLMs sometimes emit state_changes as a stringified JSON object; coerce it.
        if isinstance(state_changes, str):
            stripped = state_changes.strip()
            if stripped.startswith("{"):
                try:
                    state_changes = json.loads(stripped)
                except Exception:
                    pass
        artifacts_raw = args.get("artifacts") or []
        # LLMs sometimes emit artifacts as a stringified JSON array; coerce it.
        if isinstance(artifacts_raw, str):
            stripped = artifacts_raw.strip()
            if stripped.startswith("["):
                try:
                    artifacts_raw = json.loads(stripped)
                except Exception:
                    pass
        artifacts_arg = artifacts_raw if isinstance(artifacts_raw, list) else []

        player_id = ctx["player_id"]
        game_state: 'GameState' = ctx["game_state"]
        applied: List[str] = []

        # ── Phase 1: Apply state changes (if any) ──
        if state_changes and isinstance(state_changes, dict):
            # Respect capture_only: strip node.state writes during perception
            if bool(ctx.get("capture_only")):
                node_changes = state_changes.get("nodes")
                if isinstance(node_changes, dict):
                    sanitized_nodes: Dict[str, Any] = {}
                    stripped_node_ids: List[str] = []
                    for node_id, node_patch in node_changes.items():
                        if not isinstance(node_patch, dict):
                            sanitized_nodes[node_id] = node_patch
                            continue
                        sanitized_patch = dict(node_patch)
                        if "state" in sanitized_patch:
                            sanitized_patch.pop("state", None)
                            stripped_node_ids.append(node_id)
                        if sanitized_patch:
                            sanitized_nodes[node_id] = sanitized_patch
                    if stripped_node_ids:
                        logger.warning(
                            "Ignoring node.state writes during capture_only commit for nodes: %s",
                            ", ".join(stripped_node_ids),
                        )
                        state_changes = dict(state_changes)
                        if sanitized_nodes:
                            state_changes["nodes"] = sanitized_nodes
                        else:
                            state_changes.pop("nodes", None)

            try:
                applied = await self._apply_world_event_state_changes(state_changes, ctx)
            except Exception as e:
                logger.error(f"commit state_changes failed: {e}", exc_info=True)
                return {"error": f"Failed to apply state_changes: {str(e)}"}

        # ── Phase 2: Validate and record artifacts ──
        recorded_artifacts: List[Dict[str, Any]] = []
        for entry in artifacts_arg:
            if not isinstance(entry, dict):
                continue
            kind = entry.get("kind")
            payload = entry.get("payload")
            if not kind or payload is None:
                continue

            artifact: Dict[str, Any] = {
                "kind": kind,
                "payload": self._make_serializable(payload) if isinstance(payload, dict) else payload,
            }
            if kind == ARTIFACT_KIND_NARRATIVE:
                artifact["audience"] = entry.get("audience", "players_here")
                artifact["target_player_ids"] = list(entry.get("target_player_ids") or [])
                artifact["location_id"] = entry.get("location_id")
                artifact["exclude_player_ids"] = list(entry.get("exclude_player_ids") or [])
            elif kind == ARTIFACT_KIND_STRUCTURED:
                artifact["summary"] = (entry.get("summary") or "").strip()

            recorded_artifacts.append(artifact)
            ctx["artifacts"].append(artifact)

        if not recorded_artifacts and not applied:
            return {"error": "commit requires at least artifacts or state_changes"}

        # ── Phase 3: Record the commit event ──
        narrative_artifacts = [a for a in recorded_artifacts if a["kind"] == ARTIFACT_KIND_NARRATIVE]
        all_target_ids: List[str] = []
        for art in narrative_artifacts:
            for tid in art.get("target_player_ids", []):
                if tid not in all_target_ids:
                    all_target_ids.append(tid)
        if not all_target_ids:
            all_target_ids = [player_id]

        event_record = self._record_world_event(
            ctx,
            deliveries=[
                {
                    "narrative_length": len(a["payload"]) if isinstance(a["payload"], str) else 0,
                    "audience": a.get("audience", "players_here"),
                    "target_player_ids": a.get("target_player_ids", []),
                }
                for a in narrative_artifacts
            ],
            state_applied=applied,
            target_player_ids=all_target_ids,
            version=game_state.version,
        )

        await self._maybe_schedule_background_materialization(ctx, game_state, player_id, applied)

        # ── Phase 4: Deliver artifacts to clients ──
        await self._deliver_artifacts(ctx, recorded_artifacts, applied)

        result: Dict[str, Any] = {
            "status": "committed",
            "artifacts_recorded": len(recorded_artifacts),
            "state_paths_applied": len(applied),
            **event_record,
        }

        if len(narrative_artifacts) == 1:
            result["narrative_length"] = len(narrative_artifacts[0]["payload"]) if isinstance(narrative_artifacts[0]["payload"], str) else 0
        structured_artifacts = [a for a in recorded_artifacts if a["kind"] == ARTIFACT_KIND_STRUCTURED]
        if structured_artifacts:
            result["structured_count"] = len(structured_artifacts)

        return result

    async def _deliver_artifacts(
        self,
        ctx: Dict[str, Any],
        artifacts: List[Dict[str, Any]],
        state_applied: List[str],
    ) -> None:
        """Deliver recorded artifacts to players according to upper-layer policy.

        This method is the single point where artifact-to-client delivery
        decisions are made.  It replaces the delivery_policy checks that
        previously lived inside _tool_commit_world_event.
        """
        if not artifacts:
            return

        player_id = ctx["player_id"]
        game_state: 'GameState' = ctx["game_state"]
        task_profile = ctx.get("task_profile", TASK_PROFILE_WORLD_ACTION)
        capture_only = bool(ctx.get("capture_only"))
        is_background = task_profile == TASK_PROFILE_BACKGROUND_SIMULATION
        allow_narrative = bool(ctx.get("background_allow_player_facing_narrative", True))
        already_streamed = bool(ctx.get("_narrative_already_streamed"))

        narrative_artifacts = [a for a in artifacts if a["kind"] == ARTIFACT_KIND_NARRATIVE]
        structured_artifacts = [a for a in artifacts if a["kind"] == ARTIFACT_KIND_STRUCTURED]

        # ── Deliver structured artifacts ──
        for art in structured_artifacts:
            recorded = {
                "result": art["payload"],
                "summary": art.get("summary", ""),
                "task_type": ctx.get("task_type"),
                "task_profile": task_profile,
            }
            ctx["structured_results"].append(recorded)
            ctx["structured_result"] = recorded

        # ── Deliver narrative artifacts ──
        suppress_narrative = (
            (is_background and not allow_narrative)
            or task_profile == TASK_PROFILE_UI_DECISION
        )

        for index, art in enumerate(narrative_artifacts):
            narrative_text = art["payload"]
            if not isinstance(narrative_text, str) or not narrative_text:
                continue

            art_audience = art.get("audience", "players_here")
            art_target_ids = art.get("target_player_ids", [])
            art_location_id = art.get("location_id")
            art_exclude_ids = art.get("exclude_player_ids", [])

            delivery_targets = self._resolve_message_targets(
                game_state, player_id,
                audience_scope=art_audience,
                target_player_ids=art_target_ids,
                location_id=art_location_id,
                exclude_player_ids=art_exclude_ids,
            )
            if not delivery_targets:
                delivery_targets = [player_id]

            if capture_only:
                primary_target = delivery_targets[0]
                processed = self.game_kernel.text_processor.process_text_for_hyperlinks(
                    narrative_text, game_state, primary_target
                )
                ctx["displayed_messages"].append({
                    "text": processed,
                    "type": "game",
                    "audience": art_audience,
                    "target_player_ids": list(delivery_targets),
                    "state_applied": state_applied,
                })
            elif suppress_narrative:
                logger.info(
                    "Suppressing narrative delivery for %s task (profile=%s): %s...",
                    ctx.get("task_type"), task_profile, narrative_text[:200],
                )
            else:
                is_solo_actor = len(delivery_targets) == 1 and delivery_targets[0] == player_id
                actor_already_streamed = already_streamed and index == 0

                if actor_already_streamed and player_id in delivery_targets:
                    processed = self.game_kernel.text_processor.process_text_for_hyperlinks(
                        narrative_text, game_state, player_id
                    )
                    frontend = self.game_kernel.frontend_adapter
                    if frontend:
                        client_type = frontend.player_sessions.get(
                            player_id, {}
                        ).get('client_type', 'web')
                        final_html = frontend.format_for_client(processed, client_type)
                        await frontend.send_stream_end(player_id, final_html=final_html)
                    other_targets = [t for t in delivery_targets if t != player_id]
                    if other_targets:
                        await self._stream_text_to_players(
                            narrative_text, other_targets, game_state, "game",
                            stream_to_actor=False,
                        )
                elif actor_already_streamed:
                    frontend = self.game_kernel.frontend_adapter
                    if frontend:
                        await frontend.send_stream_end(player_id)
                    processed = await self._stream_text_to_players(
                        narrative_text, delivery_targets, game_state, "game",
                        stream_to_actor=False,
                    )
                else:
                    processed = await self._stream_text_to_players(
                        narrative_text,
                        delivery_targets,
                        game_state,
                        "game",
                        stream_to_actor=(len(narrative_artifacts) == 1 and is_solo_actor),
                    )

                actor_location = game_state.get_player_location(player_id)
                history_location = (
                    art_location_id
                    or self._infer_message_location(game_state, delivery_targets, actor_location)
                )

                ctx["displayed_messages"].append({
                    "text": processed,
                    "type": "game",
                    "audience": art_audience,
                    "target_player_ids": list(delivery_targets),
                    "state_applied": state_applied,
                })

                game_state.add_message_to_history(
                    role="companion",
                    content=processed,
                    player_ids=list(delivery_targets),
                    location=history_location,
                    metadata={
                        "event_type": "architect_commit",
                        "message_type": "game",
                        "audience": art_audience,
                        "targets": list(delivery_targets),
                        "location_id": history_location,
                        "delivery_index": index,
                        "delivery_count": len(narrative_artifacts),
                        "state_applied": state_applied[:5] if state_applied else [],
                    },
                )

        if already_streamed:
            ctx.pop("_narrative_already_streamed", None)

    async def _tool_commit_world_event(self, args: Dict, ctx: Dict) -> Dict:
        """Legacy shim: convert commit_world_event args to commit() format and delegate."""

        def _coerce_json_value(value: Any) -> Any:
            if not isinstance(value, str):
                return value
            stripped = value.strip()
            if not stripped:
                return value
            if stripped[0] not in "[{":
                return value
            try:
                return json.loads(stripped)
            except Exception:
                return value

        def _coerce_string_list(value: Any) -> List[str]:
            coerced = _coerce_json_value(value)
            if isinstance(coerced, list):
                return [item for item in coerced if isinstance(item, str)]
            if isinstance(coerced, str) and coerced:
                return [coerced]
            return []

        # ── Convert to artifacts ──
        narrative = args.get("narrative", "")
        deliveries_arg = _coerce_json_value(args.get("deliveries") or [])
        audience = args.get("audience", "players_here")
        target_player_ids = _coerce_string_list(args.get("target_player_ids") or [])
        location_id = args.get("location_id")
        exclude_player_ids = _coerce_string_list(args.get("exclude_player_ids") or [])

        artifacts: List[Dict[str, Any]] = []
        if narrative:
            artifacts.append({
                "kind": ARTIFACT_KIND_NARRATIVE,
                "payload": narrative,
                "audience": audience,
                "target_player_ids": target_player_ids,
                "location_id": location_id,
                "exclude_player_ids": exclude_player_ids,
            })
        for entry in (deliveries_arg if isinstance(deliveries_arg, list) else []):
            if not isinstance(entry, dict):
                continue
            entry_narrative = entry.get("narrative", "")
            if not entry_narrative:
                continue
            artifacts.append({
                "kind": ARTIFACT_KIND_NARRATIVE,
                "payload": entry_narrative,
                "audience": entry.get("audience", "players_here"),
                "target_player_ids": _coerce_string_list(entry.get("target_player_ids") or []),
                "location_id": entry.get("location_id"),
                "exclude_player_ids": _coerce_string_list(entry.get("exclude_player_ids") or []),
            })

        commit_args: Dict[str, Any] = {}
        if artifacts:
            commit_args["artifacts"] = artifacts
        state_changes = args.get("state_changes")
        if state_changes:
            commit_args["state_changes"] = state_changes

        return await self._tool_commit(commit_args, ctx)

    async def _maybe_schedule_background_materialization(
        self,
        ctx: Dict[str, Any],
        game_state: "GameState",
        player_id: str,
        applied: List[str],
    ) -> None:
        """Queue deferred world-enrichment work after immediate authoritative commits."""
        if ctx.get("capture_only"):
            return
        if ctx.get("background_materialization"):
            return
        if ctx.get("suppress_background_materialization"):
            return

        task_type = ctx.get("task_type")
        if task_type not in {"player_input", "process_form_result"}:
            return

        frontend = self.game_kernel.frontend_adapter
        session_id = ctx.get("session_id")
        if not session_id and frontend:
            session_id = frontend.player_sessions.get(player_id, {}).get("session_id")
        if not session_id:
            return

        source_node_id = game_state.get_player_location(player_id)
        base_version = game_state.version
        has_created_stub = any(entry.endswith("(created)") for entry in applied)

        self.game_kernel.schedule_background_materialization(
            session_id=session_id,
            player_id=player_id,
            base_version=base_version,
            reason="scene_enrichment",
            source_node_id=source_node_id,
            visible_node_id=source_node_id,
            local_only=True,
            max_new_entities=2,
            max_nodes_to_touch=1,
            max_actions_to_add=2,
            applied_changes=applied,
        )
        if has_created_stub:
            self.game_kernel.schedule_background_materialization(
                session_id=session_id,
                player_id=player_id,
                base_version=base_version,
                reason="stub_followup",
                source_node_id=source_node_id,
                visible_node_id=source_node_id,
                local_only=True,
                max_new_entities=2,
                max_nodes_to_touch=1,
                max_actions_to_add=2,
                applied_changes=applied,
            )
        self.game_kernel.schedule_background_materialization(
            session_id=session_id,
            player_id=player_id,
            base_version=base_version,
            reason="nearby_world_simulation",
            source_node_id=source_node_id,
            visible_node_id=source_node_id,
            local_only=False,
            max_new_entities=1,
            max_nodes_to_touch=2,
            max_actions_to_add=1,
            applied_changes=applied,
        )

    async def _tool_update_entity(self, args: Dict, ctx: Dict) -> Dict:
        """Compatibility helper that maps legacy update requests to merge-patch writes."""
        game_state: 'GameState' = ctx["game_state"]
        player_id = ctx["player_id"]

        entity_type = args.get("entity_type", "")
        entity_id = args.get("entity_id", "")
        updates = args.get("updates") or {}

        if not entity_type or not entity_id or not isinstance(updates, dict):
            return {"error": "entity_type, entity_id, and updates are required"}

        patch: Dict[str, Any]
        if entity_type == "node":
            node_patch: Dict[str, Any] = {}
            if "name" in updates:
                node_patch["name"] = updates["name"]
            if "definition" in updates:
                node_patch["definition"] = updates["definition"]
            if "state" in updates:
                node_patch["state"] = updates["state"]
            if updates.get("properties_set"):
                node_patch["properties"] = dict(updates["properties_set"])
            patch = {"nodes": {entity_id: node_patch}}
        elif entity_type in {"character", "player"}:
            target_id = entity_id
            if entity_type == "player":
                target_id = game_state.get_controlled_character_id(player_id)
                if not target_id:
                    return {"error": "player has no controlled character"}
            char_patch: Dict[str, Any] = {}
            if "name" in updates:
                char_patch["name"] = updates["name"]
            if "definition" in updates:
                char_patch["definition"] = updates["definition"]
            if "is_playable" in updates:
                char_patch["is_playable"] = updates["is_playable"]
            if "state" in updates:
                char_patch["state"] = updates["state"]
            if "memory_append" in updates:
                existing_memory = list(game_state.character_states.get(target_id, {}).get("memory", []))
                existing_memory.append(updates["memory_append"])
                char_patch["memory"] = existing_memory
            if updates.get("properties_set"):
                char_patch["properties"] = dict(updates["properties_set"])
            patch = {"character_states": {target_id: char_patch}}
            entity_id = target_id
            entity_type = "character"
        elif entity_type == "object":
            obj_patch: Dict[str, Any] = {}
            if "name" in updates:
                obj_patch["name"] = updates["name"]
            if "definition" in updates:
                obj_patch["definition"] = updates["definition"]
            if "state" in updates:
                obj_patch["state"] = updates["state"]
            if updates.get("properties_set"):
                obj_patch["properties"] = dict(updates["properties_set"])
            patch = {"object_states": {entity_id: obj_patch}}
        else:
            return {"error": f"Unsupported entity_type: {entity_type}"}

        applied = game_state.apply_merge_patch(patch, player_id)

        location_id = self._get_entity_location(game_state, entity_type, entity_id)
        target_players = [player_id]
        if location_id:
            target_players = game_state.get_players_in_location(location_id)
            if player_id not in target_players:
                target_players.append(player_id)

        try:
            await self._push_state_to_players(game_state, target_players)
        except Exception as e:
            logger.error(f"_tool_update_entity: failed to push state: {e}")

        return {
            "status": "updated",
            "entity_type": entity_type,
            "entity_id": entity_id,
            "state_applied": applied,
        }

    async def _tool_queue_materialization(self, args: Dict, ctx: Dict) -> Dict:
        """Compatibility helper that creates lightweight entity stubs immediately."""
        game_state: 'GameState' = ctx["game_state"]
        player_id = ctx["player_id"]

        entities = args.get("entities", [])
        if not isinstance(entities, list) or not entities:
            return {"status": "empty", "count": 0}

        current_node_id = game_state.get_player_location(player_id)
        queued_count = 0

        for entry in entities:
            entity_type = entry.get("entity_type")
            data = entry.get("entity_data", {}) or {}
            entity_id = data.get("id")
            if not entity_type or not entity_id:
                continue

            if entity_type == "object":
                placement = data.get("location", current_node_id) or current_node_id
                patch: Dict[str, Any] = {
                    "object_states": {
                        entity_id: {
                            "name": data.get("name", entity_id),
                            "definition": data.get("definition", ""),
                            "state": data.get("brief", ""),
                            "properties": {},
                        }
                    }
                }
                if placement == "inventory":
                    controlled_char_id = game_state.get_controlled_character_id(player_id)
                    if controlled_char_id:
                        existing_inventory = game_state.character_states.get(controlled_char_id, {}).get("properties", {}).get("inventory", [])
                        inventory_ids = [getattr(item, "id", item) for item in existing_inventory]
                        if entity_id not in inventory_ids:
                            inventory_ids.append(entity_id)
                        patch["character_states"] = {
                            controlled_char_id: {"properties": {"inventory": inventory_ids}}
                        }
                elif placement:
                    node = game_state.nodes.get(placement)
                    existing_ids = [obj.id for obj in node.objects] if node else []
                    if entity_id not in existing_ids:
                        existing_ids.append(entity_id)
                    patch["nodes"] = {placement: {"objects": existing_ids}}
                game_state.apply_merge_patch(patch, player_id)
                queued_count += 1

            elif entity_type == "character":
                placement = data.get("location", current_node_id) or current_node_id
                patch = {
                    "character_states": {
                        entity_id: {
                            "name": data.get("name", entity_id),
                            "definition": data.get("definition", ""),
                            "state": data.get("brief", ""),
                            "memory": [],
                            "properties": {
                                "status": [],
                                "inventory": [],
                                "location": placement,
                            },
                        }
                    }
                }
                game_state.apply_merge_patch(patch, player_id)
                queued_count += 1

            elif entity_type == "action" and current_node_id:
                node = game_state.nodes.get(current_node_id)
                existing_actions = []
                if node and node.actions:
                    for action in node.actions:
                        existing_actions.append({
                            "id": action.id,
                            "text": action.text or action.description or action.id,
                            "intent": getattr(action, "intent", None),
                        })
                if not any(action["id"] == entity_id for action in existing_actions):
                    existing_actions.append({
                        "id": entity_id,
                        "text": data.get("text", data.get("name", entity_id)),
                    })
                    game_state.apply_merge_patch(
                        {"nodes": {current_node_id: {"actions": existing_actions}}},
                        player_id,
                    )
                    queued_count += 1

        return {"status": "queued", "count": queued_count}

    async def _tool_roll_dice(self, args: Dict, ctx: Dict) -> Dict:
        """Roll dice using standard notation."""
        import random

        dice_str = args.get("dice", "1d6")
        reason = args.get("reason", "")

        # Parse dice notation: NdS+M or NdS-M
        match = re.match(r'(\d+)d(\d+)([+-]\d+)?', dice_str)
        if not match:
            return {"error": f"Invalid dice notation: {dice_str}"}

        num_dice = int(match.group(1))
        num_sides = int(match.group(2))
        modifier = int(match.group(3)) if match.group(3) else 0

        rolls = [random.randint(1, num_sides) for _ in range(num_dice)]
        total = sum(rolls) + modifier

        result = {
            "dice": dice_str,
            "rolls": rolls,
            "modifier": modifier,
            "total": total,
        }
        if reason:
            result["reason"] = reason

        logger.info(f"Architect roll_dice: {dice_str} = {rolls} + {modifier} = {total} ({reason})")
        ctx["_last_roll_result"] = result
        return result

    # ═══════════════════════════════════════════════════════════════════════════
    # Helper Methods
    # ═══════════════════════════════════════════════════════════════════════════

    def _infer_message_location(
        self,
        game_state: 'GameState',
        target_player_ids: List[str],
        fallback_location: Optional[str],
    ) -> Optional[str]:
        """Infer the most appropriate location for a message history entry."""
        if not target_player_ids:
            return fallback_location

        locations = {
            game_state.get_player_location(target_player_id)
            for target_player_id in target_player_ids
            if game_state.get_player_location(target_player_id)
        }
        if len(locations) == 1:
            return next(iter(locations))
        return fallback_location

    def _get_nonplayable_characters_at_node(self, game_state: 'GameState', node_id: Optional[str]) -> List[str]:
        """Return non-playable character IDs currently present at a node."""
        if not node_id:
            return []
        return game_state.get_npcs_in_node(node_id)

    def _build_player_summary(self, game_state: 'GameState', target_player_id: str) -> Optional[Dict[str, Any]]:
        """Build a prompt/tool-friendly summary of a player."""
        player_data = game_state.variables.get("players", {}).get(target_player_id)
        if player_data is None:
            return None

        frontend = self.game_kernel.frontend_adapter
        session_entry = frontend.player_sessions.get(target_player_id, {}) if frontend else {}
        location = game_state.get_player_location(target_player_id)
        controlled_character_id = game_state.get_controlled_character_id(target_player_id)
        inventory = game_state.get_player_inventory(target_player_id)
        summary = {
            "player_id": target_player_id,
            "name": session_entry.get("name") or player_data.get("name") or target_player_id,
            "location": location,
            "controlled_character_id": controlled_character_id,
            "inventory": [],
        }
        for item_id in inventory:
            resolved = game_state.resolve_inventory_object(item_id)
            summary["inventory"].append({
                "id": item_id,
                "name": resolved.name if resolved else item_id,
            })

        if controlled_character_id:
            char_state = game_state.character_states.get(controlled_character_id, {})
            char_props = char_state.get("properties", {})
            summary["status"] = char_props.get("status", [])
            summary["stats"] = char_props.get("stats", {})
            char_def = game_state.story.get_character(controlled_character_id) if game_state.story else None
            if char_def:
                summary["character_name"] = char_def.name
                summary["character_state"] = char_state.get("state", char_def.state) or ""

        return summary

    def _get_player_summaries_at_location(
        self,
        game_state: 'GameState',
        actor_player_id: str,
        node_id: Optional[str],
    ) -> List[Dict[str, Any]]:
        """Return summaries of other players in the same location."""
        if not node_id:
            return []
        summaries = []
        for target_player_id in game_state.get_players_in_location(node_id, exclude_player_id=actor_player_id):
            summary = self._build_player_summary(game_state, target_player_id)
            if summary:
                summaries.append(summary)
        return summaries

    def _get_session_player_summaries(self, game_state: 'GameState', actor_player_id: str) -> List[Dict[str, Any]]:
        """Return summaries of all other players currently connected to the session."""
        frontend = self.game_kernel.frontend_adapter
        if not frontend:
            return []
        actor_session_id = frontend.player_sessions.get(actor_player_id, {}).get("session_id")
        if not actor_session_id:
            return []

        summaries = []
        for target_player_id, session_data in frontend.player_sessions.items():
            if target_player_id == actor_player_id:
                continue
            if session_data.get("session_id") != actor_session_id:
                continue
            summary = self._build_player_summary(game_state, target_player_id)
            if summary:
                summaries.append(summary)
        return summaries

    def _format_player_summary_for_prompt(self, summary: Dict[str, Any]) -> str:
        """Format a player summary as a concise prompt line."""
        parts = [
            f"- {summary.get('player_id')} ({summary.get('name')})",
            f"location={summary.get('location') or '(unknown)'}",
        ]
        if summary.get("controlled_character_id"):
            char_name = summary.get("character_name") or summary["controlled_character_id"]
            parts.append(f"character={char_name}")
        status = summary.get("status") or []
        if status:
            parts.append(f"status={status}")
        return ", ".join(parts)

    def _resolve_message_targets(
        self,
        game_state: 'GameState',
        actor_player_id: str,
        audience_scope: str = "self",
        target_player_ids: Optional[List[str]] = None,
        location_id: Optional[str] = None,
        exclude_player_ids: Optional[List[str]] = None,
    ) -> List[str]:
        """Resolve message audience to concrete player IDs."""
        target_player_ids = target_player_ids or []
        exclude_player_ids = set(exclude_player_ids or [])

        if audience_scope == "self":
            resolved = [actor_player_id]
        elif audience_scope == "players_here":
            location = location_id or game_state.get_player_location(actor_player_id)
            resolved = [actor_player_id] + game_state.get_players_in_location(location, exclude_player_id=actor_player_id)
        elif audience_scope == "location_players":
            resolved = game_state.get_players_in_location(location_id) if location_id else []
        elif audience_scope == "session":
            frontend = self.game_kernel.frontend_adapter
            session_id = frontend.player_sessions.get(actor_player_id, {}).get("session_id") if frontend else None
            resolved = []
            if frontend and session_id:
                for target_player_id, session_data in frontend.player_sessions.items():
                    if session_data.get("session_id") == session_id:
                        resolved.append(target_player_id)
        elif audience_scope == "specific_players":
            resolved = list(target_player_ids)
        else:
            resolved = [actor_player_id]

        deduped = []
        for target_player_id in resolved:
            if target_player_id in exclude_player_ids:
                continue
            if target_player_id not in deduped:
                deduped.append(target_player_id)
        return deduped

    async def _send_text_to_player(self, text: str, player_id: str, message_type: str = "game"):
        """Send text to one player via the frontend adapter."""
        if self.game_kernel.frontend_adapter:
            await self.game_kernel.frontend_adapter.send_game_message(
                text, player_id, message_type=message_type
            )
        else:
            logger.warning(f"Architect: no frontend adapter to send text to player {player_id}")

    async def _stream_text_to_players(
        self,
        text: str,
        player_ids: List[str],
        game_state: 'GameState',
        message_type: str = "game",
        stream_to_actor: bool = True,
    ) -> str:
        """Send text to one or more players, streaming only when appropriate.

        Processes hyperlinks, then delivers the text in small chunks to give
        a streaming UX. Returns the processed text.
        """
        if not player_ids:
            return ""

        primary_player_id = player_ids[0]
        frontend = self.game_kernel.frontend_adapter
        if frontend:
            if stream_to_actor and len(player_ids) == 1:
                processed = self.game_kernel.text_processor.process_text_for_hyperlinks(
                    text, game_state, primary_player_id
                )
                client_type = frontend.player_sessions.get(primary_player_id, {}).get('client_type', 'web')
                final_html = frontend.format_for_client(processed, client_type)
                await frontend.send_stream_start(primary_player_id, message_type)
                chunk_size = 20
                for i in range(0, len(processed), chunk_size):
                    await frontend.send_stream_token(primary_player_id, processed[i:i + chunk_size])
                    await asyncio.sleep(0.01)
                await frontend.send_stream_end(primary_player_id, final_html=final_html)
                return processed
            else:
                primary_processed = ""
                for target_player_id in player_ids:
                    processed = self.game_kernel.text_processor.process_text_for_hyperlinks(
                        text, game_state, target_player_id
                    )
                    if not primary_processed:
                        primary_processed = processed
                    await frontend.send_game_message(processed, target_player_id, message_type=message_type)
                return primary_processed
        else:
            primary_processed = ""
            for target_player_id in player_ids:
                processed = self.game_kernel.text_processor.process_text_for_hyperlinks(
                    text, game_state, target_player_id
                )
                if not primary_processed:
                    primary_processed = processed
                await self._send_text_to_player(processed, target_player_id, message_type)
            return primary_processed

    def _get_entity_location(
        self,
        game_state: 'GameState',
        entity_type: str,
        entity_id: str,
    ) -> Optional[str]:
        """Resolve the location whose occupants could perceive an entity's visible change."""
        if entity_type == "node":
            return entity_id
        if entity_type == "character":
            return game_state.character_locations.get(entity_id) or game_state.get_character_property(
                entity_id, "location"
            )
        if entity_type == "object":
            for node_id, node in game_state.nodes.items():
                if any(obj.id == entity_id for obj in node.objects):
                    return node_id
        return None

    async def _push_state_to_players(self, game_state: 'GameState', player_ids: List[str]) -> None:
        """Push fresh game_state snapshots to a concrete list of players."""
        frontend = self.game_kernel.frontend_adapter
        if not frontend:
            return

        from src.adapters.utils.game_state_serializer import build_game_state_dict

        seen = set()
        for target_player_id in player_ids:
            if target_player_id in seen:
                continue
            seen.add(target_player_id)
            session_id = frontend.player_sessions.get(target_player_id, {}).get("session_id")
            if not session_id:
                continue
            game_state_dict = await build_game_state_dict(
                game_state,
                session_id,
                target_player_id,
            )
            frontend._format_game_state_for_player(game_state_dict, target_player_id)
            await frontend.send_json_message({
                "type": "game_state",
                "content": game_state_dict,
            }, target_player_id)
            # Do not re-render perception here.  This method is called after
            # background materialization and timed events to push updated
            # game_state (objects, characters, etc.).  The player already has
            # the scene text from a prior narration or explicit perception
            # request; triggering a full Architect render_perception call
            # would be expensive and redundant.

    # ═══════════════════════════════════════════════════════════════════════════
    # Narrative Streaming Parser
    # ═══════════════════════════════════════════════════════════════════════════

    class _NarrativeStreamExtractor:
        """Incremental JSON parser that extracts the ``narrative`` string value
        from a ``commit_world_event`` tool-call argument stream and forwards
        each chunk to the player via WebSocket as it arrives.

        Handles JSON string escapes (``\\n``, ``\\"``, ``\\\\``, ``\\t``,
        ``\\/``, ``\\uXXXX``) so the player receives clean text.
        """

        # Parser states
        _SCANNING_KEY = 0       # looking for "narrative" key
        _AFTER_KEY = 1          # saw the key, waiting for ':'
        _AFTER_COLON = 2        # saw ':', waiting for opening '"'
        _IN_VALUE = 3           # inside the narrative string value
        _DONE = 4               # closing '"' found or abandoned

        _ESCAPE_MAP = {
            '"': '"', '\\': '\\', '/': '/', 'n': '\n',
            'r': '\r', 't': '\t', 'b': '\b', 'f': '\f',
        }

        def __init__(self, frontend_adapter, player_id: str):
            self._frontend = frontend_adapter
            self._player_id = player_id
            self._state = self._SCANNING_KEY
            self._buf = ""           # small lookahead buffer
            self._escape_pending = False
            self._unicode_buf = ""   # for \uXXXX sequences
            self._stream_started = False
            self._streamed_chars = 0

        @property
        def did_stream(self) -> bool:
            return self._stream_started

        async def feed(self, chunk: str) -> None:
            """Feed a new argument chunk and forward any narrative text."""
            self._buf += chunk
            await self._consume()

        async def finish(self) -> None:
            """Signal end of stream; close the player-side stream if open."""
            # stream_end is sent later by commit_world_event with final_html
            pass

        async def _consume(self) -> None:
            while self._buf and self._state not in (self._DONE,):
                if self._state == self._SCANNING_KEY:
                    idx = self._buf.find('"narrative"')
                    if idx == -1:
                        # Keep last 12 chars in case "narrative" spans chunks
                        if len(self._buf) > 12:
                            self._buf = self._buf[-12:]
                        return
                    self._buf = self._buf[idx + len('"narrative"'):]
                    self._state = self._AFTER_KEY

                elif self._state == self._AFTER_KEY:
                    idx = self._buf.find(':')
                    if idx == -1:
                        return  # wait for more
                    self._buf = self._buf[idx + 1:]
                    self._state = self._AFTER_COLON

                elif self._state == self._AFTER_COLON:
                    # skip whitespace
                    stripped = self._buf.lstrip()
                    if not stripped:
                        self._buf = ""
                        return
                    if stripped[0] == '"':
                        self._buf = stripped[1:]
                        self._state = self._IN_VALUE
                        # Start the player-side stream
                        if self._frontend and not self._stream_started:
                            self._stream_started = True
                            await self._frontend.send_stream_start(
                                self._player_id, "game"
                            )
                    else:
                        # Not a string value (unexpected); abandon
                        self._state = self._DONE
                        return

                elif self._state == self._IN_VALUE:
                    await self._extract_string_content()
                    return

        async def _extract_string_content(self) -> None:
            """Parse JSON string content, unescape, and forward to player."""
            out_parts: list[str] = []
            i = 0
            while i < len(self._buf):
                ch = self._buf[i]

                if self._unicode_buf is not None and len(self._unicode_buf) > 0:
                    # Accumulating \uXXXX
                    self._unicode_buf += ch
                    i += 1
                    if len(self._unicode_buf) == 4:
                        try:
                            out_parts.append(chr(int(self._unicode_buf, 16)))
                        except ValueError:
                            out_parts.append('?')
                        self._unicode_buf = ""
                    continue

                if self._escape_pending:
                    self._escape_pending = False
                    if ch == 'u':
                        self._unicode_buf = ""  # start collecting 4 hex digits
                    elif ch in self._ESCAPE_MAP:
                        out_parts.append(self._ESCAPE_MAP[ch])
                    else:
                        out_parts.append(ch)
                    i += 1
                    continue

                if ch == '\\':
                    self._escape_pending = True
                    i += 1
                    continue

                if ch == '"':
                    # End of narrative string
                    self._buf = self._buf[i + 1:]
                    self._state = self._DONE
                    # Flush remaining
                    if out_parts:
                        text = "".join(out_parts)
                        self._streamed_chars += len(text)
                        if self._frontend:
                            await self._frontend.send_stream_token(
                                self._player_id, text
                            )
                    return

                out_parts.append(ch)
                i += 1

            # Consumed entire buffer without finding closing quote
            self._buf = ""
            # If escape_pending, keep the state but don't output yet
            if out_parts:
                text = "".join(out_parts)
                self._streamed_chars += len(text)
                if self._frontend:
                    await self._frontend.send_stream_token(
                        self._player_id, text
                    )

    class _ArtifactStreamExtractor:
        """Incremental JSON parser that extracts the narrative payload from
        a ``commit`` tool-call argument stream and forwards each chunk to the
        player via WebSocket as it arrives.

        Scans for ``"kind":"narrative"`` followed by ``"payload":"..."``
        within the ``artifacts`` array.  Reuses the same JSON-string-escape
        handling as ``_NarrativeStreamExtractor``.
        """

        # Parser states
        _SCANNING_KIND = 0       # looking for "kind" key
        _AFTER_KIND_KEY = 1      # saw "kind", waiting for ':'
        _AFTER_KIND_COLON = 2    # saw ':', waiting for opening '"'
        _IN_KIND_VALUE = 3       # reading the kind string value
        _SCANNING_PAYLOAD = 4    # kind was "narrative", looking for "payload" key
        _AFTER_PAYLOAD_KEY = 5   # saw "payload", waiting for ':'
        _AFTER_PAYLOAD_COLON = 6 # saw ':', waiting for opening '"'
        _IN_PAYLOAD_VALUE = 7    # inside the payload string value → streaming
        _DONE = 8

        _ESCAPE_MAP = {
            '"': '"', '\\': '\\', '/': '/', 'n': '\n',
            'r': '\r', 't': '\t', 'b': '\b', 'f': '\f',
        }

        def __init__(self, frontend_adapter, player_id: str):
            self._frontend = frontend_adapter
            self._player_id = player_id
            self._state = self._SCANNING_KIND
            self._buf = ""
            self._escape_pending = False
            self._unicode_buf = ""
            self._stream_started = False
            self._streamed_chars = 0
            self._kind_value = ""

        @property
        def did_stream(self) -> bool:
            return self._stream_started

        async def feed(self, chunk: str) -> None:
            self._buf += chunk
            await self._consume()

        async def finish(self) -> None:
            pass

        async def _consume(self) -> None:
            while self._buf and self._state != self._DONE:
                if self._state == self._SCANNING_KIND:
                    idx = self._buf.find('"kind"')
                    if idx == -1:
                        if len(self._buf) > 8:
                            self._buf = self._buf[-8:]
                        return
                    self._buf = self._buf[idx + len('"kind"'):]
                    self._state = self._AFTER_KIND_KEY

                elif self._state == self._AFTER_KIND_KEY:
                    idx = self._buf.find(':')
                    if idx == -1:
                        return
                    self._buf = self._buf[idx + 1:]
                    self._state = self._AFTER_KIND_COLON

                elif self._state == self._AFTER_KIND_COLON:
                    stripped = self._buf.lstrip()
                    if not stripped:
                        self._buf = ""
                        return
                    if stripped[0] == '"':
                        self._buf = stripped[1:]
                        self._kind_value = ""
                        self._state = self._IN_KIND_VALUE
                    else:
                        self._state = self._SCANNING_KIND
                        self._buf = stripped

                elif self._state == self._IN_KIND_VALUE:
                    end_idx = self._buf.find('"')
                    if end_idx == -1:
                        self._kind_value += self._buf
                        self._buf = ""
                        return
                    self._kind_value += self._buf[:end_idx]
                    self._buf = self._buf[end_idx + 1:]
                    if self._kind_value == "narrative":
                        self._state = self._SCANNING_PAYLOAD
                    else:
                        self._state = self._SCANNING_KIND

                elif self._state == self._SCANNING_PAYLOAD:
                    idx = self._buf.find('"payload"')
                    if idx == -1:
                        # Check if we've left the current artifact object
                        brace_idx = self._buf.find('}')
                        if brace_idx != -1:
                            self._buf = self._buf[brace_idx + 1:]
                            self._state = self._SCANNING_KIND
                            continue
                        if len(self._buf) > 12:
                            self._buf = self._buf[-12:]
                        return
                    self._buf = self._buf[idx + len('"payload"'):]
                    self._state = self._AFTER_PAYLOAD_KEY

                elif self._state == self._AFTER_PAYLOAD_KEY:
                    idx = self._buf.find(':')
                    if idx == -1:
                        return
                    self._buf = self._buf[idx + 1:]
                    self._state = self._AFTER_PAYLOAD_COLON

                elif self._state == self._AFTER_PAYLOAD_COLON:
                    stripped = self._buf.lstrip()
                    if not stripped:
                        self._buf = ""
                        return
                    if stripped[0] == '"':
                        self._buf = stripped[1:]
                        self._state = self._IN_PAYLOAD_VALUE
                        if self._frontend and not self._stream_started:
                            self._stream_started = True
                            await self._frontend.send_stream_start(
                                self._player_id, "game"
                            )
                    else:
                        self._state = self._DONE
                        return

                elif self._state == self._IN_PAYLOAD_VALUE:
                    await self._extract_string_content()
                    return

        async def _extract_string_content(self) -> None:
            """Parse JSON string content, unescape, and forward to player."""
            out_parts: list[str] = []
            i = 0
            while i < len(self._buf):
                ch = self._buf[i]

                if self._unicode_buf is not None and len(self._unicode_buf) > 0:
                    self._unicode_buf += ch
                    i += 1
                    if len(self._unicode_buf) == 4:
                        try:
                            out_parts.append(chr(int(self._unicode_buf, 16)))
                        except ValueError:
                            out_parts.append('?')
                        self._unicode_buf = ""
                    continue

                if self._escape_pending:
                    self._escape_pending = False
                    if ch == 'u':
                        self._unicode_buf = ""
                    elif ch in self._ESCAPE_MAP:
                        out_parts.append(self._ESCAPE_MAP[ch])
                    else:
                        out_parts.append(ch)
                    i += 1
                    continue

                if ch == '\\':
                    self._escape_pending = True
                    i += 1
                    continue

                if ch == '"':
                    self._buf = self._buf[i + 1:]
                    self._state = self._DONE
                    if out_parts:
                        text = "".join(out_parts)
                        self._streamed_chars += len(text)
                        if self._frontend:
                            await self._frontend.send_stream_token(
                                self._player_id, text
                            )
                    return

                out_parts.append(ch)
                i += 1

            self._buf = ""
            if out_parts:
                text = "".join(out_parts)
                self._streamed_chars += len(text)
                if self._frontend:
                    await self._frontend.send_stream_token(
                        self._player_id, text
                    )

    # ═══════════════════════════════════════════════════════════════════════════

    async def _streaming_llm_call(
        self, llm_provider, messages: list, game_state: 'GameState',
        player_id: str, ctx: Dict
    ):
        """Make a streaming LLM call, forwarding narrative tokens to the player.

        When the LLM generates a ``commit`` or ``commit_world_event`` tool
        call, the narrative content is streamed to the player in real-time
        via WebSocket, giving near-instant perceived responsiveness.

        Returns response_msg (SimpleNamespace with .content and .tool_calls).
        """
        stream = await llm_provider.async_client.chat.completions.create(
            model=llm_provider.model,
            messages=messages,
            tools=self._tool_definitions,
            tool_choice="auto",
            stream=True,
        )

        content_parts = []
        tool_calls_map = {}  # index -> {id, function_name, arguments}
        role = None

        # Narrative streaming belongs to tasks that deliver to players.
        extractors: Dict[int, Any] = {}
        frontend = self.game_kernel.frontend_adapter
        task_profile = ctx.get("task_profile", TASK_PROFILE_WORLD_ACTION)
        enable_narrative_streaming = (
            frontend is not None
            and not bool(ctx.get("capture_only"))
            and task_profile not in (TASK_PROFILE_UI_DECISION, TASK_PROFILE_BACKGROUND_SIMULATION)
        )

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

                            # Forward narrative tokens for commit or commit_world_event
                            if enable_narrative_streaming:
                                fn_name = entry["function_name"]
                                if fn_name == "commit" and idx not in extractors:
                                    extractors[idx] = self._ArtifactStreamExtractor(
                                        frontend, player_id
                                    )
                                elif fn_name == "commit_world_event" and idx not in extractors:
                                    extractors[idx] = self._NarrativeStreamExtractor(
                                        frontend, player_id
                                    )
                                if idx in extractors:
                                    await extractors[idx].feed(tc_delta.function.arguments)

            if delta.content:
                content_parts.append(delta.content)

        # Finalize extractors
        for ext in extractors.values():
            await ext.finish()

        # Flag in ctx so commit_world_event knows narrative was already streamed
        any_streamed = any(ext.did_stream for ext in extractors.values())
        if any_streamed:
            ctx["_narrative_already_streamed"] = True

        full_content = "".join(content_parts) if content_parts else None

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
            )
        else:
            response_msg = SimpleNamespace(
                role=role or "assistant",
                content=full_content,
                tool_calls=None,
            )

        return response_msg
