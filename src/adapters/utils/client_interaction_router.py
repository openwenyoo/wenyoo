"""Typed client interaction router for custom story frontends."""

from __future__ import annotations

from typing import Any, Dict


class ClientInteractionRouter:
    """Route typed story-app messages to the appropriate backend path."""

    async def route_message(
        self,
        handler: Any,
        websocket: Any,
        player_id: str,
        session_id: str,
        message: Dict[str, Any],
    ) -> bool:
        msg_type = message.get("type")
        if msg_type == "ui_query":
            await self._handle_ui_query(handler, websocket, player_id, session_id, message)
            return True
        if msg_type == "ui_action":
            await self._handle_ui_action(handler, websocket, player_id, session_id, message)
            return True
        if msg_type == "ui_event":
            return True
        return False

    async def _handle_ui_query(
        self,
        handler: Any,
        websocket: Any,
        player_id: str,
        session_id: str,
        message: Dict[str, Any],
    ) -> None:
        query = message.get("query")
        payload = message.get("payload") or {}
        if query == "object_actions":
            object_id = str(payload.get("object_id") or "").strip()
            if not object_id:
                await websocket.send_json({"type": "error", "content": "object_id is required for ui_query=object_actions"})
                return
            await handler._handle_get_object_actions(player_id, session_id, object_id)
            return
        if query == "initial_state":
            await handler._send_initial_state(websocket, player_id, session_id)
            return
        if query == "current_perception":
            await handler._handle_get_current_perception(websocket, player_id, session_id)
            return
        await websocket.send_json({"type": "error", "content": f"Unknown ui_query '{query}'"})

    async def _handle_ui_action(
        self,
        handler: Any,
        websocket: Any,
        player_id: str,
        session_id: str,
        message: Dict[str, Any],
    ) -> None:
        execution = message.get("execution", "architect_action")
        payload = message.get("payload") or {}

        if execution == "local":
            return

        if execution == "form_submit":
            form_message = {
                "form_id": payload.get("form_id"),
                "data": payload.get("data", {}),
                "files": payload.get("files", {}),
            }
            await handler._handle_form_submit(websocket, player_id, session_id, form_message)
            return

        if execution == "deterministic_action":
            action_id = message.get("action_id")
            if action_id == "save_game":
                await handler._handle_save_command(websocket, player_id, session_id)
                return
            if action_id == "merge_patch":
                patch = payload.get("patch")
                await handler._handle_deterministic_merge_patch(
                    websocket,
                    player_id,
                    session_id,
                    patch,
                    display_text=message.get("display_text"),
                )
                return
            if action_id == "command":
                command = str(payload.get("command") or "").strip()
                if not command:
                    await websocket.send_json({"type": "error", "content": "Missing command for deterministic ui_action"})
                    return
                if not handler._is_instant_command(command):
                    await websocket.send_json({
                        "type": "error",
                        "content": f"Deterministic ui_action command '{command}' is not instant-safe.",
                    })
                    return
                await handler._handle_game_command(
                    websocket,
                    player_id,
                    session_id,
                    command,
                    input_type=message.get("input_type", "story_app"),
                    action_hint=message.get("action_hint", ""),
                    display_text=message.get("display_text") or command,
                )
                return
            await websocket.send_json({"type": "error", "content": f"Unknown deterministic ui_action '{action_id}'"})
            return

        if execution == "architect_action":
            await handler._handle_architect_action(websocket, player_id, session_id, message)
            return

        await websocket.send_json({"type": "error", "content": f"Unknown ui_action execution '{execution}'"})
