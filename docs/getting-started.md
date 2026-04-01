# Getting Started

This guide gets the game server and the story editor running on a local machine.

## Prerequisites

- Python 3.10+
- `pip`
- Node.js 18+ only if you want to rebuild the editor
- Docker only if you prefer containerized deployment

## Quickest First Run

1. Clone the repository and enter the project directory.
2. Start the interactive launcher:

```bash
./scripts/run-linux.sh
```

On Windows PowerShell use:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-windows.ps1
```

The first run opens a setup wizard that can configure `venv`, `config.yaml`,
`.env`, API keys, base URLs, and model names. Later runs with no args show a
config-group chooser.

3. Open:
   - Game: `http://localhost:8000`
   - Editor: `http://localhost:8000/editor`

If you just want the fastest smoke test, choose the mock profile in the wizard.

## Local Python Setup

### Windows PowerShell

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run-windows.ps1
```

The run script handles first-run setup automatically, then starts the server.
With no args after setup, it shows a config-group chooser. To skip the chooser
and go straight to a known profile, pass normal server args such as:

```powershell
.\scripts\run-windows.ps1 --config-group claude
```

### macOS and Linux

```bash
./scripts/run-linux.sh
```

The run script handles first-run setup automatically, then starts the server.
With no args after setup, it shows a config-group chooser. To skip the chooser
and go straight to a known profile, pass normal server args such as:

```bash
./scripts/run-linux.sh --config-group claude
```

## Configure a Real LLM

Edit `config.yaml`:

```yaml
llm:
  provider: openai-compatible
  base_url: https://api.openai.com/v1
  model: gpt-4o-mini
  api_key_env: LLM_API_KEY
```

Then put the key in `.env`:

```env
LLM_API_KEY=your_key_here
```

Common provider setups are documented in [Configuration](configuration.md).

## Docker Setup

Build the image:

```bash
docker build -t wenyoo .
```

Run it:

```bash
docker run -p 8000:8000 \
  -v "$(pwd)/config.yaml:/app/config.yaml" \
  -v "$(pwd)/.env:/app/.env" \
  -v "$(pwd)/stories:/app/stories" \
  -v "$(pwd)/saves:/app/saves" \
  wenyoo
```

On Windows, replace `$(pwd)` with an explicit absolute path or the equivalent command syntax for your shell.

## Rebuilding the Editor

You usually do not need this. Prebuilt editor assets are already committed under `static/editor/`.

If you change files in `editor/`:

```bash
cd editor
npm install
npm run build
```

See [Editor Getting Started](editor/getting-started.md) for editor-specific behavior.

## First-Run Checklist

- `config.yaml` exists
- `.env` exists
- `python -m src.main` starts without crashing
- `http://localhost:8000` loads the player UI
- `http://localhost:8000/editor` loads the editor
- Story list appears in the player UI

## Next Docs

- [Basic Features](basic-features.md)
- [Playing Stories](playing-stories.md)
- [Writing Stories](writing-stories.md)
