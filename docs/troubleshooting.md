# Troubleshooting

## Server Does Not Start

Check:

- Python version is 3.10 or newer
- dependencies from `requirements.txt` are installed
- `config.yaml` exists
- `.env` exists if your selected provider needs a key

Try mock mode first:

```bash
python -m src.main --llm-provider mock
```

## API Key Errors

If the server says your key is missing:

- confirm the variable exists in `.env`
- confirm `api_key_env` in `config.yaml` points to the same variable name
- restart the server after editing `.env`

## Port Already In Use

Start the server on another port:

```bash
python -m src.main --port 9000
```

Then open the game and editor on the matching port.

## Editor Does Not Load

Check:

- the server is running
- `http://localhost:8000/editor` is reachable
- `static/editor/` exists

If you changed the editor source recently, rebuild it:

```bash
cd editor
npm install
npm run build
```

## Story Does Not Appear In The Story List

Check:

- the file lives under `stories/`
- the story has a valid `id`
- full stories define `start_node_id` and `nodes`
- YAML is valid

Run:

```bash
python scripts/validate_story_yaml.py stories/your_story.yaml
```

## Connection Graph Is Missing Or Stale

Compile it again:

```bash
python tools/compile_connections.py stories/your_story.yaml --write
```

Then reload the story in the editor or game.

## Editor Save Problems

Check:

- the server process can write to `stories/`
- the story ID is valid
- `editor_secret` is configured correctly if editor auth is enabled

Remember that editor saves write to the story entry file and create backups in `saves/story_versions/`.

## Windows Docker Path Issues

The sample `docker run` command uses Unix-style `$(pwd)`. On Windows:

- use an explicit absolute path
- or rewrite the mounts to match your shell syntax

## Reconnect Does Not Work

Reconnect depends on browser storage and the active session still existing on the server.

Check:

- the browser did not clear local storage
- the same browser profile is being used
- the disconnect was not longer than the server grace period

## Where To Look For Logs

- `wenyoo.log`
- terminal output from the running server

## Related Docs

- [Getting Started](getting-started.md)
- [Configuration](configuration.md)
- [Playing Stories](playing-stories.md)
- [Editor Reference](editor/reference.md)
