# Wenyoo Game Engine

[中文](README_CN.md) | English

Wenyoo is an AI-native game engine built in Python. Authors define worlds declaratively in YAML — nodes, characters, objects, and rules — and an LLM-powered Architect agent brings them to life, interpreting player intent, enforcing author-written rules, and propagating consequences across the world.

## Features

- **Declarative world authoring**: Define entities (nodes, characters, objects) with natural-language definitions that the LLM follows as rules — combat, puzzles, trade, dialogue, or any mechanic you can describe
- **LLM Architect agent**: A unified tool-calling agent interprets free-form player input, resolves actions against author-written rules, and commits world events
- **Entity model**: Each entity carries a `definition` (static rules for the LLM), `explicit_state` (what the player sees), and `properties` (mechanical state like inventory, status, and location)
- **Connection graph**: A relationship map between entities that lets the Architect propagate consequences — when a lever is pulled in one room, the effect reaches a locked cradle in another
- **Multiplayer**: Multiple players share the same world with per-player state, local speech, item handoff, and cross-room communication
- **Web-based interface**: Modern frontend with real-time WebSocket communication
- **Visual Story Editor**: React-based node graph editor for authoring and visualizing stories
- **YAML story format**: Human-readable story files with support for forms, triggers, scripted effects, and LLM-generated content

## Prerequisites

- Python 3.10 or higher
- Node.js 18+ (only if you want to rebuild the story editor)
- Docker (optional, for containerized deployment)

## Quick Start

### Option A: Docker (recommended)

1. Clone the repository:
   ```bash
   git clone <your-repo-url>
   cd wenyoo
   ```

2. Set up configuration:
   ```bash
   cp config.example.yaml config.yaml
   cp .env.example .env
   # Edit .env to add your API key
   # Edit config.yaml to configure your LLM provider
   ```

3. Build and run:
   ```bash
   docker build -t wenyoo .
   docker run -p 8000:8000 \
     -v $(pwd)/config.yaml:/app/config.yaml \
     -v $(pwd)/.env:/app/.env \
     -v $(pwd)/stories:/app/stories \
     -v $(pwd)/saves:/app/saves \
     wenyoo
   ```

4. Open your browser:
   - **Game**: http://localhost:8000
   - **Story Editor**: http://localhost:8000/editor

### Option B: Local Python

1. Clone the repository:
   ```bash
   git clone <your-repo-url>
   cd wenyoo
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   # On Windows
   venv\Scripts\activate
   # On macOS/Linux
   source venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Set up configuration:
   ```bash
   cp config.example.yaml config.yaml
   cp .env.example .env
   # Edit .env to add your API key
   # Edit config.yaml to configure your LLM provider
   ```

5. **(Optional) Build the story editor from source:**
   ```bash
   cd editor && npm install && npm run build && cd ..
   ```
   Pre-built editor files are included in `static/editor/`. You only need
   this step if you modify the editor source code.

6. Run the server:
   ```bash
   python -m src.main
   ```

7. Open your browser:
   - **Game**: http://localhost:8000
   - **Story Editor**: http://localhost:8000/editor

## Project Structure

```
Wenyoo/
├── src/                    # Game Engine (Python Backend)
│   ├── core/               # Core game logic
│   │   ├── game_kernel.py      # Main orchestrator
│   │   ├── architect.py        # Unified LLM agent (tool-calling loop)
│   │   ├── node_generator.py   # Dynamic node generation (LLM)
│   │   └── ...
│   ├── models/             # Pydantic data models
│   ├── adapters/           # External system bridges (FastAPI, LLM)
│   └── main.py             # Entry point
├── static/                 # Web Frontend
│   ├── index.html          # Game interface
│   ├── js/app.js           # Game client logic
│   ├── css/style.css       # Game styles
│   └── editor/             # Story Editor (compiled)
├── editor/                 # Story Editor Source (React/Vite)
├── stories/                # Story content (YAML files)
├── prompts/                # LLM prompt templates
└── saves/                  # Saved game states
```

## Configuration

The engine uses a YAML configuration file (`config.yaml`), environment variables (`.env`), and optional CLI overrides.

### Quick Setup

```bash
# Copy example files
cp config.example.yaml config.yaml
cp .env.example .env

# Add API keys to .env as needed
echo "LLM_API_KEY=your_openai_compatible_key_here" >> .env
echo "CLAUDE_API_KEY=your_claude_key_here" >> .env
```

### Config Groups

`config.yaml` can define shared top-level settings plus named groups under `config_groups`. If you do not pass `--config-group`, the loader automatically uses `config_groups.default`.

```yaml
server:
  host: 127.0.0.1
  port: 8000

config_groups:
  default:
    llm:
      provider: openai-compatible
      base_url: https://api.openai.com/v1
      model: gpt-4o-mini
      api_key_env: LLM_API_KEY

  claude:
    llm:
      provider: claude
      model: claude-sonnet-4-6
      api_key_env: CLAUDE_API_KEY
```

### Precedence

For overlapping values, settings are applied in this order:

1. Built-in defaults
2. Shared top-level values from `config.yaml`
3. The selected `config_groups.<name>` block, or `config_groups.default`
4. Environment variable overrides such as `LLM_PROVIDER`
5. Explicit CLI flags such as `--llm-provider` or `--port`

### Command-line Options

```bash
python -m src.main [options]
```

| Option | Description |
|--------|-------------|
| `--config PATH` | Path to `config.yaml` |
| `--config-group NAME` | Config group to load from `config_groups` |
| `--llm-provider TYPE` | LLM provider: `openai-compatible`, `ollama`, `claude`, `mock` |
| `--llm-base-url URL` | LLM API base URL |
| `--llm-model NAME` | Model name to use |
| `--host HOST` | Server host (default: from config) |
| `--port PORT` | Server port (default: from config) |

**Examples:**
```bash
# Use config_groups.default from config.yaml
python -m src.main

# Use the claude group from config.yaml
python -m src.main --config-group claude

# Quick test with mock LLM (no API needed)
python -m src.main --config-group mock

# Override one field on top of the selected group
python -m src.main --config-group claude --port 9000

# Use local vLLM server without editing the file
python -m src.main --llm-base-url http://localhost:8080/v1 --llm-model mistral-7b
```

## Creating Stories

Stories are defined in YAML files, but the full format is large enough that the best starting point is the dedicated documentation rather than a shortened README example.

Start here:

- **[Writing Stories](docs/writing-stories.md)** - Recommended authoring workflow, validation, examples, and how the editor fits in
- **[Story Format Guide](prompts/story_format_description.md)** - Canonical top-level story schema
- **[Node & Effects Reference](prompts/node_format_description.md)** - Canonical node, action, trigger, and effect schema

### Story Structure

- **id**: Unique identifier for the story
- **name**: Story title
- **start_node_id**: Starting node
- **initial_variables**: Story-wide variables, counters, flags, lore, and derived values
- **nodes**: Story locations or scenes, authored with the DSPP model:
  - **definition**: What the node is and how it should behave
  - **explicit_state**: What the player currently perceives
  - **properties**: Mechanical state and custom structured data
  - plus local **actions**, **objects**, and **triggers**
- **objects**: World objects also use DSPP:
  - **definition**: Identity and authored interaction rules
  - **explicit_state**: Visible current presentation
  - **properties**: Mechanical state such as containment, status, or custom fields
- **characters**: Characters use DSPPM:
  - **definition**: Identity, personality, and behavior rules
  - **explicit_state**: What is visibly true now
  - **properties**: Stats, location, inventory, status, and other mechanics
  - **memory**: Accumulated interaction history for that character

If you want the detailed authored schema, use the dedicated docs above rather than treating this README summary as complete.

## Story Editor

The visual story editor allows you to create and edit stories using a node-based graph interface.

**[Editor Overview](docs/editor/README.md)** - Entry page for the story editor docs

### Building the Editor

```bash
cd editor
npm install
npm run build
```

The built files are automatically copied to `static/editor/`.

## Story Authoring Documentation

For detailed documentation on creating stories:

- **[Story Format Guide](prompts/story_format_description.md)** - Complete guide to story YAML structure
- **[Node & Effects Reference](prompts/node_format_description.md)** - Detailed reference for nodes, triggers, actions, and effects

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Community

Join the official Wenyoo Discord server for announcements, support, and discussion:

[Official Discord Server](https://discord.gg/ZjaHZqCACG)

If you are viewing this README on desktop, scan the QR code below to join on your phone:

![Wenyoo Discord QR code](docs/assets/wenyoo-discord-qrcode.png)
