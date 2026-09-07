# Two-player co-op test

Run from the repository root after installing `requirements.txt` and
`requirements-test.txt`:

```sh
WENYOO_E2E_REPORT_DIR=test_outputs/two-player-coop \
  .venv/bin/python -m pytest tests/e2e/test_two_player_coop.py -q
```

The test starts a local Uvicorn server on an available loopback port and connects
two separate WebSocket clients, Alpha and Beta. It copies
`stories/multiplayer_coop_demo.yaml` into a temporary directory and uses temporary
saves. It takes about 17 seconds, including the story's real 15-second lever timer.
Both servers and both clients shut down at the end.

It checks character assignment, separate phone identities and properties, nearby
speech, distance phone delivery, shared power and its timed reset, atomic item
handoff, rejection of duplicate ownership, vault completion, and reconnecting
both players after a server restart. Each reconnect must restore only that
player's visible transcript and preserve their character and inventory.

The model boundary uses scripted tool calls. The actual server, streaming tool
assembly, commit validation, message routing, state mutation, ticker and disk
persistence run normally. Puzzle decisions are scripted: this test does **not**
measure natural-language understanding, real-provider latency, or browser UI
behavior. Those require a separate live-model/browser playthrough.

Optional report files contain completed checks and each client's wire transcript.
Session tokens are omitted. A failed run may contain only the checks completed
before the failure; the pytest result determines overall success.

Narratives are delivered after a complete tool call is accepted. Sending text
while its JSON arguments are still arriving can reveal recipient-only text to
the actor or announce success for a commit that later fails validation. The
phone and invalid-inventory steps guard against both regressions.
