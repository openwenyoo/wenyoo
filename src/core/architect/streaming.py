"""_StreamingMixin"""
import logging
from types import SimpleNamespace
from typing import Any, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from src.models.game_state import GameState

from src.core.architect.task import (
    TASK_PROFILE_WORLD_ACTION,
    TASK_PROFILE_BACKGROUND_SIMULATION,
)

logger = logging.getLogger(__name__)


class _StreamingMixin:
    """Mixin for Architect: streaming LLM call + incremental stream extractors."""
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
            and task_profile != TASK_PROFILE_BACKGROUND_SIMULATION
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
