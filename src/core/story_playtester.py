"""Bounded breadth-first playtesting through the real Architect, in isolated sessions."""
import asyncio
from collections import deque
import copy
import hashlib
import json
from pathlib import Path
import tempfile

import yaml

from src.core.game_kernel import GameKernel
from src.core.state_manager import StateManager
from src.core.story_manager import StoryManager
from src.models.game_state import GameState


def state_fingerprint(state):
    return hashlib.sha256(json.dumps({
        "variables": state.variables,
        "characters": state.character_states,
        "objects": state.object_states,
        "nodes": {key: node.model_dump() for key, node in state.nodes.items()},
    }, sort_keys=True, default=str).encode()).hexdigest()


async def playtest_story(data, llm_provider, *, max_steps=8, max_depth=4, commands=None):
    """Explore authored actions/sample commands; report observed outcomes, never claim exhaustive coverage."""
    report = {"steps": [], "findings": [], "visited_nodes": [], "ending_nodes": [],
              "limited": False, "status": "completed", "max_steps": max_steps}
    player = "playtester"

    def finding(code, message, node_id=None, path=None):
        report["findings"].append({"code": code, "message": message, "entity_id": node_id,
                                   "entity_type": "node", "severity": "warning", "path": path or []})

    with tempfile.TemporaryDirectory(prefix="wenyoo-playtest-") as directory:
        payload = copy.deepcopy(data)
        payload.pop("includes", None)
        payload.update(id="playtest", title=data.get("title", data.get("name", "Playtest")))
        Path(directory, "playtest.yaml").write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")
        kernel = GameKernel(StoryManager(directory), StateManager(str(Path(directory, "saves"))), llm_provider)
        try:
            state = await asyncio.wait_for(kernel.start_new_game_async(
                "playtest", player, notify_observers=False, proactive_generation=False,
                character_id=next((c["id"] for c in payload.get("characters", []) if c.get("is_playable")), None),
            ), timeout=45)
            if state is None:
                raise ValueError("Story could not start; check its initial triggers and player defaults.")
            queue = deque([(state, [], frozenset(), bool(kernel._pending_forms))])
            explored = set()
            while queue and len(report["steps"]) < max_steps:
                state, path, ancestors, awaiting_form = queue.popleft()
                node_id = state.get_player_location(player)
                if node_id not in report["visited_nodes"]:
                    report["visited_nodes"].append(node_id)
                node = state.nodes.get(node_id)
                if not node:
                    finding("invalid_location", f"Player reached missing node '{node_id}'.", node_id, path)
                    continue
                if node.is_ending:
                    if node_id not in report["ending_nodes"]:
                        report["ending_nodes"].append(node_id)
                    continue
                if awaiting_form or state.save_metadata.get("pending_clarifications", {}).get(player):
                    finding("input_required", "This path needs a form response or clarification; supply a dedicated manual test.", node_id, path)
                    kernel._pending_forms.clear()
                    continue
                fingerprint = state_fingerprint(state)
                if fingerprint in explored:
                    continue
                explored.add(fingerprint)
                if len(path) >= max_depth:
                    report["limited"] = True
                    continue
                actions = []
                for action in [*node.actions, *state.story.actions]:
                    if action.is_available(state, player)[0]:
                        actions.append((action.text or action.id, "action_click", action.intent or ""))
                actions.extend((command, "typed", "") for command in (commands or []))
                if not actions:
                    finding("dead_end", "No available authored actions or sample commands at this non-ending node. Free-text paths may still exist.", node_id, path)
                for command, input_type, hint in actions:
                    if len(report["steps"]) >= max_steps:
                        report["limited"] = True
                        break
                    # Runtime updates may change definitions as well as state. Copy both for every branch.
                    branch_story = state.story.model_copy(deep=True)
                    branch = GameState.from_dict(copy.deepcopy(state.to_dict()), branch_story)
                    kernel.story_manifest = branch_story
                    kernel.current_game_state = branch
                    kernel._pending_forms.clear()
                    step_path = path + [command]
                    try:
                        result = await asyncio.wait_for(kernel.process_input(
                            command, branch, branch_story, player, input_type=input_type, action_hint=hint,
                        ), timeout=45)
                        branch.validate_inventory_ownership()
                        after_id = branch.get_player_location(player)
                        step = {"command": command, "from": node_id, "to": after_id,
                                "path": step_path, "narrative": result.get("narrative_response", "")}
                        report["steps"].append(step)
                        if after_id in branch.nodes and after_id not in report["visited_nodes"]:
                            report["visited_nodes"].append(after_id)
                        if after_id not in branch.nodes:
                            finding("invalid_location", f"Action moved the player to unknown node '{after_id}'.", node_id, step_path)
                        elif kernel._pending_forms or branch.save_metadata.get("pending_clarifications", {}).get(player):
                            finding("input_required", "This action requests a form response or clarification.", after_id, step_path)
                        elif result.get("fallback_used"):
                            finding("no_response", "The Architect returned its fallback instead of completing this action.", node_id, step_path)
                        elif branch.nodes[after_id].is_ending:
                            if after_id not in report["ending_nodes"]:
                                report["ending_nodes"].append(after_id)
                        elif state_fingerprint(branch) in ancestors | {fingerprint}:
                            finding("loop", "This path repeats an earlier world state (possibly an intentional inspection action).", node_id, step_path)
                        else:
                            queue.append((branch, step_path, ancestors | {fingerprint}, False))
                    except Exception as exc:
                        report["steps"].append({"command": command, "from": node_id, "path": step_path, "error": str(exc) or type(exc).__name__})
                        finding("runtime_error", str(exc) or type(exc).__name__, node_id, step_path)
            if queue:
                report["limited"] = True
        except Exception as exc:
            report["status"] = "failed"
            finding("startup_error", str(exc) or type(exc).__name__)
        finally:
            # No live adapter, ticker, persistent saves, or deferred generation is used.
            tasks = list(kernel._generation_in_progress.values())
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
        report["unvisited_nodes"] = sorted(set(payload.get("nodes", {})) - set(report["visited_nodes"]))
    return report
