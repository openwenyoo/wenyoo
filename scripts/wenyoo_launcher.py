#!/usr/bin/env python3
from __future__ import annotations

import getpass
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config.yaml"
ENV_PATH = REPO_ROOT / ".env"
ENV_EXAMPLE_PATH = REPO_ROOT / ".env.example"
REQUIREMENTS_PATH = REPO_ROOT / "requirements.txt"
METADATA_PATH = REPO_ROOT / ".wenyoo-launcher.json"


DEFAULT_METADATA: dict[str, Any] = {
    "version": 1,
    "use_venv": True,
    "runtime_python": "",
    "requirements_synced_at": "",
    "preferred_group": "default",
}


PROVIDER_PRESETS: dict[str, dict[str, str]] = {
    "openai-compatible": {
        "label": "OpenAI-compatible",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "api_key_env": "LLM_API_KEY",
    },
    "claude": {
        "label": "Claude",
        "model": "claude-sonnet-4-6",
        "api_key_env": "CLAUDE_API_KEY",
    },
    "ollama": {
        "label": "Ollama",
        "base_url": "http://localhost:11434/v1",
        "model": "llama3",
        "api_key_env": "LLM_API_KEY",
    },
    "mock": {
        "label": "Mock",
        "model": "mock",
        "api_key_env": "LLM_API_KEY",
    },
}


def main() -> int:
    launcher_args, server_args = split_launcher_args(sys.argv[1:])
    metadata = load_metadata()
    existing_setup = is_setup_usable(metadata)

    if launcher_args["configure"]:
        selected_group = run_setup_wizard(metadata)
    elif not existing_setup:
        if is_interactive():
            selected_group = run_setup_wizard(metadata)
        else:
            selected_group = bootstrap_defaults(metadata)
    else:
        selected_group = None

    runtime_python = get_runtime_python(load_metadata())

    if requirements_need_sync(load_metadata()):
        sync_requirements(runtime_python)
        metadata = load_metadata()
    else:
        metadata = load_metadata()

    if launcher_args["setup_only"]:
        print("Setup complete.")
        return 0

    passthrough_args = list(server_args)
    if selected_group and not has_config_group_arg(passthrough_args):
        passthrough_args = ["--config-group", selected_group, *passthrough_args]

    if not passthrough_args:
        if is_interactive():
            chosen = choose_run_target(metadata.get("preferred_group", "default"))
            if chosen is None:
                return 0
            if chosen == "__configure__":
                selected_group = run_setup_wizard(metadata)
                metadata = load_metadata()
                chosen = selected_group or metadata.get("preferred_group", "default")
            if chosen != "__defaults__":
                passthrough_args = ["--config-group", chosen]
        else:
            preferred_group = metadata.get("preferred_group") or "default"
            if config_group_exists(preferred_group):
                passthrough_args = ["--config-group", preferred_group]

    runtime_python = get_runtime_python(load_metadata())
    result = subprocess.run([runtime_python, "-m", "src.main", *passthrough_args], cwd=REPO_ROOT)

    used_group = extract_config_group(passthrough_args)
    if used_group:
        metadata = load_metadata()
        metadata["preferred_group"] = used_group
        save_metadata(metadata)

    return result.returncode


def split_launcher_args(args: list[str]) -> tuple[dict[str, bool], list[str]]:
    launcher_args = {"setup_only": False, "configure": False}
    passthrough: list[str] = []
    for arg in args:
        if arg == "--setup-only":
            launcher_args["setup_only"] = True
        elif arg == "--configure":
            launcher_args["configure"] = True
        else:
            passthrough.append(arg)
    return launcher_args, passthrough


def is_interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def load_metadata() -> dict[str, Any]:
    if not METADATA_PATH.exists():
        return dict(DEFAULT_METADATA)
    try:
        data = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return dict(DEFAULT_METADATA)
    merged = dict(DEFAULT_METADATA)
    merged.update(data)
    return merged


def save_metadata(data: dict[str, Any]) -> None:
    merged = dict(DEFAULT_METADATA)
    merged.update(data)
    METADATA_PATH.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")


def is_setup_usable(metadata: dict[str, Any]) -> bool:
    runtime_python = metadata.get("runtime_python", "")
    if not runtime_python:
        return False
    if not Path(runtime_python).exists():
        return False
    if not REQUIREMENTS_PATH.exists():
        return False
    return True


def bootstrap_defaults(metadata: dict[str, Any]) -> str:
    runtime_python = ensure_runtime_environment(use_venv=True)
    if not CONFIG_PATH.exists():
        write_config_file(provider="mock")
    ensure_env_file()
    sync_requirements(runtime_python)
    metadata = load_metadata()
    metadata.update(
        {
            "use_venv": True,
            "runtime_python": runtime_python,
            "preferred_group": "default",
        }
    )
    save_metadata(metadata)
    return "default"


def run_setup_wizard(metadata: dict[str, Any]) -> str:
    print("")
    print("Wenyoo Setup Wizard")
    print("===================")
    print("Inspired by the guided onboarding flow used by tools like OpenClaw.")
    print("")

    existing_runtime = metadata.get("runtime_python", "")
    default_use_venv = metadata.get("use_venv", True)
    if existing_runtime and "venv" in existing_runtime.replace("\\", "/"):
        default_use_venv = True

    use_venv = prompt_yes_no(
        "Use a virtual environment for Wenyoo dependencies?",
        default=default_use_venv,
        help_text="Recommended. Choose 'no' only if you intentionally want to install into the current Python.",
    )

    runtime_python = ensure_runtime_environment(use_venv=use_venv)

    config_action = choose_config_action()
    selected_provider = detect_default_provider_from_config() or "mock"
    if config_action == "wizard":
        selected_provider = configure_via_wizard()
    else:
        ensure_config_exists()

    env_action = choose_env_action(provider_requires_key(selected_provider))
    if env_action == "update":
        update_api_key_via_prompt(selected_provider)
    else:
        ensure_env_file()

    sync_requirements(runtime_python)
    metadata = load_metadata()

    metadata.update(
        {
            "use_venv": use_venv,
            "runtime_python": runtime_python,
            "preferred_group": "default",
        }
    )
    save_metadata(metadata)
    print("")
    print("Setup complete.")
    return "default"


def choose_config_action() -> str:
    config_exists = CONFIG_PATH.exists()
    options = []
    if config_exists:
        options.append(("keep", "Keep the existing config.yaml"))
    options.append(("wizard", "Create or replace config.yaml with the guided wizard"))
    return prompt_choice("How should config.yaml be handled?", options, default="keep" if config_exists else "wizard")


def choose_env_action(needs_api_key: bool) -> str:
    env_exists = ENV_PATH.exists()
    if needs_api_key:
        if env_exists:
            default = "update"
            options = [
                ("keep", "Keep the existing .env as-is"),
                ("update", "Review or update the API key in .env"),
            ]
        else:
            default = "update"
            options = [
                ("update", "Create .env and save the API key"),
                ("keep", "Skip API key setup for now"),
            ]
    else:
        if env_exists:
            default = "keep"
            options = [
                ("keep", "Keep the existing .env as-is"),
                ("update", "Create or refresh .env from the example file"),
            ]
        else:
            default = "update"
            options = [
                ("update", "Create .env from the example file"),
                ("keep", "Skip .env creation for now"),
            ]
    return prompt_choice("How should .env be handled?", options, default=default)


def ensure_runtime_environment(use_venv: bool) -> str:
    system_python = sys.executable
    if not system_python:
        raise RuntimeError("Python executable could not be determined.")

    if use_venv:
        venv_dir = REPO_ROOT / "venv"
        venv_python = venv_python_path()
        if not venv_dir.exists():
            print("Creating virtual environment...")
            run_command([system_python, "-m", "venv", "venv"])
        if not venv_python.exists():
            raise RuntimeError(f"{venv_python} was not found after creating the virtual environment.")
        return str(venv_python)

    return system_python


def venv_python_path() -> Path:
    if os.name == "nt":
        return REPO_ROOT / "venv" / "Scripts" / "python.exe"
    return REPO_ROOT / "venv" / "bin" / "python"


def requirements_need_sync(metadata: dict[str, Any]) -> bool:
    if not REQUIREMENTS_PATH.exists():
        return False
    synced_at = metadata.get("requirements_synced_at", "")
    if not synced_at:
        return True
    runtime_python = metadata.get("runtime_python", "")
    if not runtime_python or not Path(runtime_python).exists():
        return True
    try:
        synced_dt = datetime.fromisoformat(synced_at)
    except ValueError:
        return True
    if synced_dt.tzinfo is None:
        synced_dt = synced_dt.replace(tzinfo=timezone.utc)
    return REQUIREMENTS_PATH.stat().st_mtime > synced_dt.timestamp()


def sync_requirements(runtime_python: str) -> None:
    install_requirements(runtime_python)
    metadata = load_metadata()
    metadata["requirements_synced_at"] = datetime.now(timezone.utc).isoformat()
    metadata["runtime_python"] = runtime_python
    save_metadata(metadata)


def install_requirements(runtime_python: str) -> None:
    print("")
    print(f"Using Python: {runtime_python}")
    print("Installing Python dependencies...")
    run_command([runtime_python, "-m", "pip", "install", "--upgrade", "pip"])
    run_command([runtime_python, "-m", "pip", "install", "-r", str(REQUIREMENTS_PATH)])


def ensure_config_exists() -> None:
    if not CONFIG_PATH.exists():
        write_config_file(provider="mock")


def ensure_env_file() -> None:
    if ENV_PATH.exists():
        return
    if ENV_EXAMPLE_PATH.exists():
        shutil.copyfile(ENV_EXAMPLE_PATH, ENV_PATH)
    else:
        ENV_PATH.write_text("", encoding="utf-8")


def configure_via_wizard() -> str:
    provider = prompt_choice(
        "Choose your primary provider",
        [
            ("openai-compatible", "OpenAI-compatible API"),
            ("claude", "Anthropic Claude"),
            ("ollama", "Ollama"),
            ("mock", "Mock provider for local testing"),
        ],
        default="openai-compatible",
    )

    group = {
        "provider": provider,
        "model": prompt_text("Model name", default=PROVIDER_PRESETS[provider]["model"]),
    }

    if provider in ("openai-compatible", "ollama"):
        group["base_url"] = prompt_text("Base URL", default=PROVIDER_PRESETS[provider]["base_url"])

    if provider != "ollama" and provider != "mock":
        group["api_key_env"] = prompt_text("API key environment variable name", default=PROVIDER_PRESETS[provider]["api_key_env"])
    elif provider == "openai-compatible":
        group["api_key_env"] = prompt_text("API key environment variable name", default=PROVIDER_PRESETS[provider]["api_key_env"])

    add_mock_group = provider != "mock" and prompt_yes_no("Also add a mock config group for quick local testing?", default=True)

    if CONFIG_PATH.exists():
        backup_path = backup_file(CONFIG_PATH)
        print(f"Backed up existing config.yaml to {backup_path.name}")

    write_config_file(provider=provider, group=group, add_mock_group=add_mock_group)
    return provider


def write_config_file(provider: str, group: dict[str, str] | None = None, add_mock_group: bool | None = None) -> None:
    group = group or {"provider": provider, "model": PROVIDER_PRESETS[provider]["model"]}
    if provider in ("openai-compatible", "ollama"):
        group.setdefault("base_url", PROVIDER_PRESETS[provider]["base_url"])
    if provider in ("openai-compatible", "claude"):
        group.setdefault("api_key_env", PROVIDER_PRESETS[provider]["api_key_env"])
    if add_mock_group is None:
        add_mock_group = provider != "mock"

    lines = [
        "# Generated by the Wenyoo setup wizard.",
        "# Re-run ./scripts/run-linux.sh or .\\scripts\\run-windows.ps1 to reconfigure.",
        "",
        "server:",
        "  host: 127.0.0.1",
        "  port: 8000",
        "",
        "paths:",
        "  stories_dir: stories",
        "  saves_dir: saves",
        "  static_dir: static",
        "",
        "logging:",
        "  level: INFO",
        "  file: wenyoo.log",
        "",
        "forms:",
        "  enabled: true",
        "  max_file_size_mb: 20.0",
        "  max_text_length: 100000",
        "  save_original_files: false",
        "  upload_dir: data/uploads",
        "  allowed_file_types:",
        "    - text/plain",
        "    - application/pdf",
        "    - text/markdown",
        "    - text/csv",
        "    - application/json",
        "",
        "config_groups:",
        "  default:",
        "    llm:",
        f"      provider: {group['provider']}",
    ]

    if "base_url" in group:
        lines.append(f"      base_url: {group['base_url']}")
    lines.append(f"      model: {group['model']}")
    if "api_key_env" in group:
        lines.append(f"      api_key_env: {group['api_key_env']}")
    lines.extend(
        [
            "      timeout_connect: 10.0",
            "      timeout_read: 120.0",
        ]
    )

    if add_mock_group:
        lines.extend(
            [
                "",
                "  mock:",
                "    llm:",
                "      provider: mock",
                "      model: mock",
            ]
        )

    CONFIG_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def update_api_key_via_prompt(provider: str) -> None:
    ensure_env_file()

    if provider not in PROVIDER_PRESETS:
        return
    if provider in ("mock", "ollama"):
        print("The selected provider does not require an API key. Keeping .env available for future use.")
        return

    env_var = PROVIDER_PRESETS[provider]["api_key_env"]
    if CONFIG_PATH.exists():
        for line in CONFIG_PATH.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("api_key_env:"):
                env_var = stripped.split(":", 1)[1].strip()
                break

    api_key = getpass.getpass(f"Enter a value for {env_var} (leave blank to keep current value): ").strip()
    if not api_key:
        print("Leaving the API key unchanged.")
        return

    update_env_var(env_var, api_key)
    print(f"Saved {env_var} to .env")


def update_env_var(key: str, value: str) -> None:
    lines: list[str] = []
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()

    updated = False
    for index, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[index] = f"{key}={value}"
            updated = True
            break

    if not updated:
        if lines and lines[-1] != "":
            lines.append("")
        lines.append(f"{key}={value}")

    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def choose_run_target(preferred_group: str) -> str | None:
    groups = list_config_groups()
    options: list[tuple[str, str]] = []

    if groups:
        for group in groups:
            label = group
            if group == preferred_group:
                label = f"{group} (last used)"
            options.append((group, f"Run with config group '{label}'"))
    else:
        options.append(("__defaults__", "Run with config.yaml defaults"))

    options.extend(
        [
            ("__configure__", "Open the setup wizard"),
            ("__quit__", "Quit"),
        ]
    )

    choice = prompt_choice("Choose how to start Wenyoo", options, default=preferred_group if preferred_group in groups else options[0][0])
    if choice == "__quit__":
        return None
    return choice


def list_config_groups() -> list[str]:
    if not CONFIG_PATH.exists():
        return []

    groups: list[str] = []
    in_section = False
    section_indent = 0
    for raw_line in CONFIG_PATH.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(raw_line) - len(raw_line.lstrip(" "))
        if stripped == "config_groups:":
            in_section = True
            section_indent = indent
            continue

        if not in_section:
            continue

        if indent <= section_indent:
            break

        if indent == section_indent + 2 and stripped.endswith(":"):
            groups.append(stripped[:-1])

    return groups


def detect_default_provider_from_config() -> str | None:
    if not CONFIG_PATH.exists():
        return None

    lines = CONFIG_PATH.read_text(encoding="utf-8").splitlines()
    in_default = False
    in_llm = False
    default_indent = None
    llm_indent = None

    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        indent = len(raw_line) - len(raw_line.lstrip(" "))

        if stripped == "config_groups:":
            in_default = False
            in_llm = False
            default_indent = None
            llm_indent = None
            continue

        if stripped == "default:":
            in_default = True
            in_llm = False
            default_indent = indent
            llm_indent = None
            continue

        if in_default and default_indent is not None and indent <= default_indent:
            in_default = False
            in_llm = False
            default_indent = None
            llm_indent = None

        if in_default and stripped == "llm:":
            in_llm = True
            llm_indent = indent
            continue

        if in_llm and llm_indent is not None and indent <= llm_indent:
            in_llm = False
            llm_indent = None

        if in_llm and stripped.startswith("provider:"):
            return stripped.split(":", 1)[1].strip()

    return None


def config_group_exists(group_name: str) -> bool:
    return group_name in list_config_groups()


def has_config_group_arg(args: list[str]) -> bool:
    return any(arg == "--config-group" or arg.startswith("--config-group=") for arg in args)


def extract_config_group(args: list[str]) -> str | None:
    for index, arg in enumerate(args):
        if arg == "--config-group" and index + 1 < len(args):
            return args[index + 1]
        if arg.startswith("--config-group="):
            return arg.split("=", 1)[1]
    return None


def get_runtime_python(metadata: dict[str, Any]) -> str:
    runtime_python = metadata.get("runtime_python", "")
    if runtime_python and Path(runtime_python).exists():
        return runtime_python
    raise RuntimeError("Wenyoo is not configured yet. Run the setup wizard first.")


def provider_requires_key(provider: str) -> bool:
    return provider in ("openai-compatible", "claude")


def prompt_text(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    while True:
        value = input(f"{prompt}{suffix}: ").strip()
        if value:
            return value
        if default is not None:
            return default
        print("A value is required.")


def prompt_yes_no(prompt: str, default: bool = True, help_text: str | None = None) -> bool:
    if help_text:
        print(help_text)
    suffix = "[Y/n]" if default else "[y/N]"
    while True:
        value = input(f"{prompt} {suffix}: ").strip().lower()
        if not value:
            return default
        if value in ("y", "yes"):
            return True
        if value in ("n", "no"):
            return False
        print("Please answer yes or no.")


def prompt_choice(prompt: str, options: list[tuple[str, str]], default: str | None = None) -> str:
    print("")
    print(prompt)
    for index, (_, label) in enumerate(options, start=1):
        default_marker = ""
        if default is not None and options[index - 1][0] == default:
            default_marker = " [default]"
        print(f"  {index}. {label}{default_marker}")

    default_index = None
    if default is not None:
        for index, (value, _) in enumerate(options, start=1):
            if value == default:
                default_index = index
                break

    while True:
        raw_value = input("Enter choice number: ").strip()
        if not raw_value and default_index is not None:
            return options[default_index - 1][0]
        if raw_value.isdigit():
            choice_index = int(raw_value)
            if 1 <= choice_index <= len(options):
                return options[choice_index - 1][0]
        print("Please enter one of the listed numbers.")


def backup_file(path: Path) -> Path:
    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    backup_path = path.with_name(f"{path.name}.{timestamp}.bak")
    shutil.copyfile(path, backup_path)
    return backup_path


def run_command(command: list[str]) -> None:
    subprocess.run(command, cwd=REPO_ROOT, check=True)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nCancelled.")
        raise SystemExit(1)
