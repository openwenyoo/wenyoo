"""_PromptMixin"""
import json
import logging
import os
import re
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.models.game_state import GameState
    from src.models.story_models import Story

from src.core.architect.task import (
    ArchitectTask,
    infer_task_profile,
)

logger = logging.getLogger(__name__)


class _PromptMixin:
    """Mixin for Architect: _PromptMixin"""
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
            "read_game_state, commit, roll_dice, read_node, and "
            "queue_materialization. "
            "Use commit to narrate AND record state changes atomically."
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

        if task.task_type in (
            "player_input",
            "execute_intent",
            "guided_intent",
            "scene_interaction",
            "character_interaction",
            "tool_assisted_decision",
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
                    "broader world context. Use commit() for all state "
                    "changes. If the selected action should open a story-defined form, "
                    "call present_form(form_id) and stop instead of narrating the "
                    "selection as ordinary text."
                )
            else:
                parts.append(
                    "Resolve this purpose-driven task from the supplied context. "
                    "Treat the supplied framing as guidance, not "
                    "as authoritative world truth. Use the current world state and tools "
                    "to decide what actually happens. Use commit() for all "
                    "player-visible or consequential outcomes. If the task should collect "
                    "structured input before continuing, call present_form(form_id) and stop."
                )

            parts.append("")
            parts.append(
                "## PROFILE RULES: WORLD ACTION\n"
                "This task resolves real in-world action. If it causes a player-facing or consequential outcome, "
                "use commit(). If structured input is required first, use present_form(form_id)."
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
                    "include those creations in the same commit state_changes patch.\n"
                    "Call commit ONCE with the rendered perception. "
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
                "- Use commit with state_changes; omit player-facing narrative unless connected players should immediately perceive the result.\n"
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
                "commit state_changes patch before narrating.\n"
                "- set_controlled_character(target=X): write "
                "variables.players.<player_id>.controlled_character_id = X\n"
                "- goto_node(target=Y): move the relevant embodied character by writing "
                "character_states.<char_id>.properties.location = Y and update "
                "visited_nodes when the player newly reaches that node\n"
                "Narrate from the resulting controlled character and resulting location. "
                "Call commit ONCE, then STOP."
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
                "apply them through commit(state_changes=...). Narrate the "
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
