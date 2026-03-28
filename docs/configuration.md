# Configuration

Runtime configuration comes from `config.yaml`, environment variables, and optional CLI overrides.

## Core Files

- `config.example.yaml`: documented baseline configuration
- `config.yaml`: your local runtime config
- `.env.example`: example environment variables
- `.env`: your local secrets and overrides

## `config.yaml`

The config loader supports two layers inside `config.yaml`:

- shared top-level settings that apply to every run
- named config groups under `config_groups`

If `config_groups` is present, `python -m src.main` automatically loads `config_groups.default` unless you pass `--config-group NAME`.

### Example Layout

```yaml
server:
  host: 127.0.0.1
  port: 8000

paths:
  stories_dir: stories
  saves_dir: saves
  static_dir: static

config_groups:
  default:
    llm:
      provider: openai-compatible
      base_url: https://api.openai.com/v1
      model: gpt-4o-mini
      api_key_env: LLM_API_KEY
      timeout_connect: 10.0
      timeout_read: 120.0

  claude:
    llm:
      provider: claude
      model: claude-sonnet-4-6
      api_key_env: CLAUDE_API_KEY

  mock:
    llm:
      provider: mock
```

### What Can Go In A Group

Each config group can override any standard section:

- `llm`
- `server`
- `paths`
- `logging`
- `forms`

That means a group can change more than the model provider. For example, you can keep the same `server` and `paths` for every run, or override `server.port` in a specific group.

### LLM

The main LLM keys are:

- `provider`
- `base_url`
- `model`
- `api_key_env`
- `timeout_connect`
- `timeout_read`

Typical `provider` values:

- `openai-compatible`
- `ollama`
- `claude`
- `mock`

Use `openai-compatible` for OpenAI, DashScope, vLLM, LM Studio, Together.ai, and similar endpoints.

Use `claude` for Anthropic Claude models. Claude does not use `base_url`; set `model` and point `api_key_env` at an environment variable such as `CLAUDE_API_KEY`.

### Server

Important keys:

- `host`
- `port`
- `editor_secret`

`host: 127.0.0.1` is the safe local default.

If you expose `0.0.0.0` for LAN access, read the editor auth notes below.

### Paths

The server reads these from `paths`:

- `stories_dir`
- `saves_dir`
- `static_dir`

### Logging

Important logging keys:

- `level`
- `file`

By default, file logging writes to `wenyoo.log`.

## Precedence

For overlapping values, runtime settings are applied in this order:

1. Built-in defaults in the Python config dataclasses
2. Shared top-level values from `config.yaml`
3. The selected `config_groups.<name>` block, or `config_groups.default`
4. Environment variable overrides
5. Explicit CLI flags

This means `--port` still wins over the selected group, and environment variables such as `LLM_MODEL` can still override values from the file.

## Environment Variables

Common variables include:

- `LLM_API_KEY`
- `CLAUDE_API_KEY`
- `LLM_PROVIDER`
- `LLM_BASE_URL`
- `LLM_MODEL`
- `SERVER_HOST`
- `SERVER_PORT`
- `LOG_LEVEL`

The API key variable name is not fixed. `config.yaml` decides which variable to read through `api_key_env`.

## CLI Overrides

`python -m src.main` supports overrides such as:

- `--config`
- `--config-group`
- `--llm-provider`
- `--llm-base-url`
- `--llm-model`
- `--host`
- `--port`
- `--stories-dir`
- `--saves-dir`
- `--static-dir`
- `--log-level`

Use CLI flags when you need one-off runs without editing `config.yaml`.

Example commands:

```bash
python -m src.main
python -m src.main --config-group claude
python -m src.main --config-group mock
python -m src.main --config-group claude --port 9000
```

## Suggested Groups

### Local testing

- `provider: mock`
- `host: 127.0.0.1`
- no `editor_secret` required

### Real local authoring

- `provider: openai-compatible`, `claude`, or `ollama`
- `host: 127.0.0.1`
- optional `editor_secret`

### LAN or shared machine

- review firewall and reverse proxy settings
- set `editor_secret`
- avoid exposing the editor openly without auth

## Editor Auth

The editor can save stories and invoke editing APIs. If the server is reachable beyond localhost, set `server.editor_secret` in `config.yaml`.

When `editor_secret` is configured:

- editor write endpoints require the `X-Editor-Token` header
- the editor UI can receive the token through the `editor_token` query parameter and store it locally

If you are working on a trusted local machine only, leaving `editor_secret` unset is acceptable for development.

## Related Docs

- [Getting Started](getting-started.md)
- [Troubleshooting](troubleshooting.md)
