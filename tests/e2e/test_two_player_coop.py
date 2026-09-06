"""Two independent network clients play the shipped co-op example.

The LLM boundary is scripted; Uvicorn, WebSockets, Architect streaming/commit,
audience routing, inventories and disk persistence are real. This validates
engine wiring, not a model's ability to infer the author's puzzle rules.

Set WENYOO_E2E_REPORT_DIR to retain both clients' redacted wire transcripts.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import shutil
import socket

import uvicorn
from websockets.asyncio.client import connect

from src.adapters.web_frontend_adapter import WebFrontendAdapter
from src.core.game_kernel import GameKernel
from src.core.state_manager import StateManager
from src.core.story_manager import StoryManager
from tests.helpers.mock_llm_tool_calling import ToolCallingMockLLM, tc


STORY_ID = "multiplayer_coop_demo"
ROOT = Path(__file__).resolve().parents[2]


def narrative(text, audience="self", **targets):
    return {"kind": "narrative", "payload": text, "audience": audience, **targets}


def character_patch(character, **properties):
    return {"character_states": {character: {"properties": properties}}}


@asynccontextmanager
async def running_server(workspace):
    existing_tasks = asyncio.all_tasks()
    llm = ToolCallingMockLLM()
    create = llm.async_client.chat.completions.create

    async def respond(**kwargs):
        # Peer state pushes render a fresh perception as well as the player's
        # command response. Supply those independently of the action queue.
        prompt = next(m["content"] for m in kwargs["messages"] if m["role"] == "user")
        if "Task type: render_perception" in prompt:
            renderer = ToolCallingMockLLM()
            renderer.queue_tool_calls([tc("commit", artifacts=[narrative("You survey the chamber.")])])
            return await renderer.async_client.chat.completions.create(**kwargs)
        return await create(**kwargs)

    llm.async_client.chat.completions.create = respond
    stories = StoryManager(stories_dir=str(workspace / "stories"))
    kernel = GameKernel(stories, StateManager(save_dir=str(workspace / "saves")), llm)
    adapter = WebFrontendAdapter(
        host="127.0.0.1", port=0, static_dir=str(workspace / "static"),
        game_kernel=kernel, story_manager=stories, editor_secret="",
    )
    kernel.frontend_adapter = adapter
    kernel.register_observer(adapter)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(adapter.app, log_level="error", lifespan="on"))
    task = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        async with asyncio.timeout(10):
            while not server.started:
                if task.done():
                    await task
                    raise RuntimeError("Server exited before accepting connections")
                await asyncio.sleep(0.01)
        yield f"ws://127.0.0.1:{port}/ws", adapter, llm
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(task, 10)
        finally:
            sock.close()
            pending = asyncio.all_tasks() - existing_tasks
            for background in pending:
                background.cancel()
            await asyncio.gather(*pending, return_exceptions=True)


class Player:
    """An isolated player identity and socket, retaining all received messages."""

    def __init__(self, name):
        self.name = name
        self.id = f"e2e_{name.lower()}"
        self.token = None
        self.events = []
        self.ws = None

    async def send(self, **message):
        self.events.append({"direction": "send", **message})
        await self.ws.send(json.dumps(message))

    async def until(self, message_type, *, timeout=15):
        async with asyncio.timeout(timeout):
            while True:
                message = json.loads(await self.ws.recv())
                self.events.append({"direction": "receive", **message})
                assert message.get("type") != "error", message
                if message.get("type") == message_type:
                    return message

    async def open(self, url, llm, *, rejoin=False):
        self.ws = await connect(url)
        await self.send(type="register_or_rejoin", player_id=self.id, session_token=self.token)
        message = await self.until("rejoined" if rejoin else "registered")
        if not rejoin:
            self.token = message["session_token"]
            await self.send(type="set_player_name", name=self.name)
            await self.send(type="select_story", story_id=STORY_ID)
            while (await self.until("control")).get("subtype") != "session_selection":
                pass
        return message

    async def enter(self, llm, room=None):
        await self.send(type="join_session" if room else "create_session", session_code=room, client_type="web")
        return (await self.until("game_start"))["content"]["game_state"]

    async def act(self, llm, command, *, changes=None, artifacts=None, tool_calls=None):
        llm.queue_tool_calls(tool_calls or [tc(
            "commit", artifacts=artifacts or [narrative(command)], state_changes=changes or {},
        )])
        await self.send(type="input", content=command)
        result = (await self.until("command_result"))["content"]
        assert not result["response"].get("fallback_used"), result["response"]
        assert llm.queue_size == 0, "A scripted response was not consumed"
        return result["game_state"]

    async def close(self):
        if self.ws:
            await self.ws.close()


def visible_text(events):
    """Only message fields rendered in the play UI, excluding state/debug data."""
    chunks = []
    for event in events:
        if event["direction"] != "receive":
            continue
        kind = event.get("type")
        if kind in {"game", "stream_token"}:
            chunks.append(event.get("content") or event.get("token") or "")
        elif kind == "stream_end":
            chunks.append(event.get("final_html") or "")
    return "\n".join(chunks)


async def test_two_players_complete_example_and_rejoin_after_restart(tmp_path):
    (tmp_path / "stories").mkdir()
    (tmp_path / "static").mkdir()
    shutil.copy(ROOT / "stories" / f"{STORY_ID}.yaml", tmp_path / "stories")
    alpha, beta = Player("Alpha"), Player("Beta")
    checks = []
    try:
        async with running_server(tmp_path) as (url, adapter, llm):
            await alpha.open(url, llm)
            a = await alpha.enter(llm)
            room = a["session_id"]
            await beta.open(url, llm)
            b = await beta.enter(llm, room)
            gs = adapter.game_sessions[room]["game_state"]
            assert a["player_state"]["controlled_character_id"] == "operator_alpha"
            assert b["player_state"]["controlled_character_id"] == "operator_beta"
            assert gs.get_player_inventory(alpha.id) == ["mobile_phone_alpha"]
            assert gs.get_player_inventory(beta.id) == ["mobile_phone_beta"]
            checks.append("Two players join one room with distinct characters and phones")

            await alpha.act(llm, "Mute my phone.", changes={"object_states": {
                "mobile_phone_alpha": {"properties": {"muted": True}},
            }})
            assert gs.object_states["mobile_phone_alpha"]["properties"]["muted"] is True
            assert not gs.object_states["mobile_phone_beta"]["properties"].get("muted")
            checks.append("Changing Alpha's phone properties leaves Beta's phone unchanged")

            start = len(beta.events)
            await alpha.act(llm, "Say: let's split up.", artifacts=[narrative("Alpha says: let's split up.", "players_here")])
            # A following command acts as a transport barrier for the peer socket.
            await beta.act(llm, "Go east to the relay gallery.", changes=character_patch("operator_beta", location="relay_gallery"))
            assert "let's split up" in visible_text(beta.events[start:])
            await alpha.act(llm, "Go west to the signal archive.", changes=character_patch("operator_alpha", location="signal_archive"))
            assert gs.get_player_location(beta.id) == "relay_gallery"
            assert gs.get_player_location(alpha.id) == "signal_archive"
            checks.append("Nearby speech reaches the partner; movement is per player")

            start = len(beta.events)
            await alpha.act(llm, "Say: archive-only words.", artifacts=[narrative("archive-only words", "players_here")])
            await beta.act(llm, "Take the relay lens before power arrives.", artifacts=[narrative("The cradle is magnetically locked.")])
            assert "archive-only words" not in visible_text(beta.events[start:])
            assert "relay_lens" not in gs.get_player_inventory(beta.id)
            checks.append("Local speech stays local; the scripted locked-lens reply leaves inventory unchanged")

            a_start, b_start = len(alpha.events), len(beta.events)
            await alpha.act(llm, 'Use phone to say to Beta: "ready at archive".', artifacts=[
                narrative('Alpha says to you through the phone: "ready at archive".', "specific_players", target_player_ids=[beta.id]),
                narrative("Phone connected; your message was sent to Beta."),
            ])
            await beta.act(llm, "Check my phone.", artifacts=[narrative("Your phone is ready.")])
            assert "Alpha says to you through the phone" in visible_text(beta.events[b_start:])
            assert "message was sent to Beta" not in visible_text(beta.events[b_start:])
            assert "message was sent to Beta" in visible_text(alpha.events[a_start:])
            assert "Alpha says to you through the phone" not in visible_text(alpha.events[a_start:])
            checks.append("Cross-room phone delivery shows separate sender and recipient text")

            await alpha.act(llm, "Take the tuning fork.", changes={
                **character_patch("operator_alpha", inventory=["mobile_phone_alpha", "tuning_fork"]),
                "variables": {"tuning_fork_taken": True},
            })
            b_start = len(beta.events)
            await alpha.act(llm, "Pull the phase lever.", changes={
                "variables": {"power_routed": True},
                "object_states": {"phase_lever": {"state": "Engaged, routing power."}},
                "timed_events": [{
                    "id": "phase_lever_reset", "delay_seconds": 15, "scope": "session",
                    "player_id": alpha.id, "node_id": "signal_archive",
                    "event_context": "The phase lever returns to standby; power drops in the gallery.",
                }],
            }, artifacts=[
                narrative("The phase lever engages."),
                narrative("Power arrives from the archive; the cradle releases.", "location_players", location_id="relay_gallery"),
            ])
            await beta.act(llm, "Take the relay lens.", changes={
                **character_patch("operator_beta", inventory=["mobile_phone_beta", "relay_lens"]),
                "variables": {"relay_lens_taken": True},
            })
            assert "Power arrives from the archive" in visible_text(beta.events[b_start:])
            assert gs.variables["power_routed"] is True
            checks.append("Shared power state and cross-room notifications reach the other player")

            llm.queue_tool_calls([tc("commit", state_changes={
                "variables": {"power_routed": False},
                "object_states": {"phase_lever": {"state": "Standby."}},
            }, artifacts=[
                narrative("The lever returns to standby.", "location_players", location_id="signal_archive"),
                narrative("Power drops in the gallery.", "location_players", location_id="relay_gallery"),
            ])])
            async with asyncio.timeout(20):
                while "Power drops in the gallery" not in json.dumps(await beta.until("game", timeout=20)):
                    pass
            assert gs.variables["power_routed"] is False
            assert not gs.timed_events
            assert "relay_lens" in gs.get_player_inventory(beta.id)
            checks.append("The real 15-second ticker resets power and notifies the gallery without losing the collected lens")

            for player, character in [(alpha, "operator_alpha"), (beta, "operator_beta")]:
                await player.act(llm, "Go north to the paired lock.", changes=character_patch(character, location="paired_lock"))
            await beta.act(llm, "Give Alpha the relay lens.", changes={"character_states": {
                "operator_alpha": {"properties": {"inventory": ["mobile_phone_alpha", "tuning_fork", "relay_lens"]}},
                "operator_beta": {"properties": {"inventory": ["mobile_phone_beta"]}},
            }}, artifacts=[narrative("Beta hands the relay lens to Alpha.", "players_here")])
            assert gs.get_player_inventory(beta.id) == ["mobile_phone_beta"]
            assert gs.get_player_inventory(alpha.id) == ["mobile_phone_alpha", "tuning_fork", "relay_lens"]
            gs.validate_inventory_ownership()
            checks.append("Atomic item handoff removes the lens from Beta and adds it to Alpha")

            a_start = len(alpha.events)
            version = gs.version
            # A malformed model commit must neither duplicate an item nor
            # announce its speculative success before the retry corrects it.
            llm.queue_tool_calls([tc("commit", artifacts=[narrative("Duplicated lens success.")], state_changes={
                "variables": {"invalid_duplicate": True},
                **character_patch("operator_beta", inventory=["mobile_phone_beta", "relay_lens"]),
            })])
            await alpha.act(llm, "Duplicate the lens for Beta.", artifacts=[narrative("The lens remains a single physical item.")])
            assert "Duplicated lens success" not in visible_text(alpha.events[a_start:])
            assert "invalid_duplicate" not in gs.variables
            assert "relay_lens" not in gs.get_player_inventory(beta.id)
            assert gs.version == version
            checks.append("An invalid duplicate-item commit is rejected atomically and never displays its success text")

            await alpha.act(llm, "Assemble the relay resonator.", changes={
                **character_patch("operator_alpha", inventory=["mobile_phone_alpha"]),
                "variables": {"resonator_assembled": True, "handoff_complete": True},
            }, artifacts=[narrative("The assembled resonator illuminates the dock.", "players_here")])
            await alpha.act(llm, "Take the sun console.", changes={"variables": {"players": {alpha.id: {"paired_role_sun": True}}}})
            await alpha.act(llm, "Also take the moon console.", artifacts=[narrative("A different operator must take the moon console.")])
            assert not gs.variables["paired_gate_open"]
            await beta.act(llm, "Take the moon console.", changes={"variables": {
                "players": {beta.id: {"paired_role_moon": True}}, "paired_gate_open": True,
            }}, artifacts=[narrative("The paired gate opens for both operators.", "players_here")])
            for player, character in [(alpha, "operator_alpha"), (beta, "operator_beta")]:
                await player.act(llm, "Enter the verification vault.", changes=character_patch(character, location="verification_vault"))
            assert all(gs.get_player_location(p.id) == "verification_vault" for p in (alpha, beta))
            assert gs.variables["resonator_assembled"] and gs.variables["handoff_complete"]
            checks.append("Both players reach the verification vault after complementary console inputs")

            await alpha.send(type="input", content="save")
            while "Game saved successfully" not in json.dumps(await alpha.until("game")):
                pass
            await alpha.close()
            await beta.close()

        # A fresh kernel and adapter load the room solely from disk.
        async with running_server(tmp_path) as (url, adapter, llm):
            for player, character, phone in [(alpha, "operator_alpha", "mobile_phone_alpha"), (beta, "operator_beta", "mobile_phone_beta")]:
                content = (await player.open(url, llm, rejoin=True))["content"]
                state = content["game_state"]
                assert state["session_id"] == room
                assert state["player_state"]["controlled_character_id"] == character
                assert state["player_state"]["location"] == "verification_vault"
                assert [i["id"] for i in state["player_state"]["inventory"]] == [phone]
                history = json.dumps(content["transcript"])
                expected = "message was sent to Beta" if player is alpha else "Alpha says to you through the phone"
                excluded = "Alpha says to you through the phone" if player is alpha else "message was sent to Beta"
                assert expected in history
                assert excluded not in history
            restored = adapter.game_sessions[room]["game_state"]
            assert restored.variables["paired_gate_open"] is True
            assert restored.variables["handoff_complete"] is True
            assert restored.object_states["mobile_phone_alpha"]["properties"]["muted"] is True
            assert not restored.object_states["mobile_phone_beta"]["properties"].get("muted")
            restored.validate_inventory_ownership()
            checks.append("Server restart preserves both identities, private transcripts, inventories and completed puzzle")
            await alpha.close()
            await beta.close()
    finally:
        await alpha.close()
        await beta.close()
        if report_dir := os.environ.get("WENYOO_E2E_REPORT_DIR"):
            output = Path(report_dir)
            output.mkdir(parents=True, exist_ok=True)
            for player in (alpha, beta):
                events = [{k: v for k, v in e.items() if k != "session_token"} for e in player.events]
                (output / f"{player.name.lower()}.json").write_text(json.dumps(events, indent=2), encoding="utf-8")
            (output / "checks.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
