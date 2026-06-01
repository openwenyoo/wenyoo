"""_DeliveryMixin"""
import asyncio
import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from src.models.game_state import GameState

from src.core.architect.task import (
    TASK_PROFILE_WORLD_ACTION,
    TASK_PROFILE_BACKGROUND_SIMULATION,
    ARTIFACT_KIND_NARRATIVE,
    ARTIFACT_KIND_STRUCTURED,
)

logger = logging.getLogger(__name__)


class _DeliveryMixin:
    """Mixin for Architect: _DeliveryMixin"""
    async def _deliver_artifacts(
        self,
        ctx: Dict[str, Any],
        artifacts: List[Dict[str, Any]],
        state_applied: List[str],
    ) -> None:
        """Deliver recorded artifacts to players according to upper-layer policy.

        This method is the single point where artifact-to-client delivery
        decisions are made.
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
        suppress_narrative = is_background and not allow_narrative

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
