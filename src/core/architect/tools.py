"""_ToolMixin"""
import json
import logging
import re
from typing import Any, Callable, Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from src.models.game_state import GameState
    from src.models.story_models import Story

from src.core.architect.task import (
    ARTIFACT_KIND_NARRATIVE,
    ARTIFACT_KIND_STRUCTURED,
)

logger = logging.getLogger(__name__)


class _ToolMixin:
    """Mixin for Architect: _ToolMixin"""
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
                    t_entry['conditions'] = [c.model_dump() for c in trigger.conditions]
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
                    logger.error(f"commit: failed to push characters update: {e}")

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
