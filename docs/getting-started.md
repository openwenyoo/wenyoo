# Getting Started

This guide gets the game server and the story editor running on a local machine.

## Prerequisites

- Python 3.10+
- `pip`
- Node.js 18+ only if you want to rebuild the editor
- Docker only if you prefer containerized deployment

## Quickest First Run

1. Clone the repository and enter the project directory.
2. Copy `config.example.yaml` to `config.yaml`.
3. Copy `.env.example` to `.env`.
4. Start the server with the mock provider:

```bash
python -m src.main --llm-provider mock
```

5. Open:
   - Game: `http://localhost:8000`
   - Editor: `http://localhost:8000/editor`

Mock mode is the fastest way to verify that the server, web client, and editor all start correctly.

## Local Python Setup

### Windows PowerShell

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item config.example.yaml config.yaml
Copy-Item .env.example .env
python -m src.main
```

### macOS and Linux

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml
cp .env.example .env
python -m src.main
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
