"""
Configuration loader for the AI Native game engine.

Loads configuration from config.yaml and environment variables.
Environment variables take precedence over config file values.
"""
import os
import logging
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, field

import yaml

logger = logging.getLogger(__name__)
CONFIG_GROUPS_KEY = "config_groups"


@dataclass
class LLMConfig:
    """LLM provider configuration."""
    provider: str = "mock"  # openai-compatible, ollama, mock
    base_url: str = "http://localhost:11434/v1"
    model: str = "llama3"
    api_key_env: str = "LLM_API_KEY"
    timeout_connect: float = 10.0  # Connection timeout in seconds (shorter for faster retries)
    timeout_read: float = 120.0   # Read timeout in seconds
    
    @property
    def api_key(self) -> Optional[str]:
        """Get the API key from environment variable."""
        return os.getenv(self.api_key_env)
    
    def validate(self) -> None:
        """Validate the LLM configuration."""
        valid_providers = {"openai-compatible", "ollama", "claude", "mock"}
        if self.provider not in valid_providers:
            raise ValueError(
                f"Invalid LLM provider: '{self.provider}'. "
                f"Must be one of: {', '.join(valid_providers)}"
            )
        
        if self.provider == "openai-compatible" and not self.api_key:
            raise ValueError(
                f"API key is required for openai-compatible provider. "
                f"Set the {self.api_key_env} environment variable in your .env file."
            )
        
        if self.provider == "claude" and not self.api_key:
            raise ValueError(
                f"API key is required for claude provider. "
                f"Set the {self.api_key_env} environment variable in your .env file."
            )
        
        if self.provider in ("openai-compatible", "ollama") and not self.base_url:
            raise ValueError(
                f"base_url is required for {self.provider} provider."
            )


@dataclass
class ServerConfig:
    """Server configuration."""
    host: str = "127.0.0.1"
    port: int = 8000
    editor_secret: Optional[str] = None


@dataclass
class PathsConfig:
    """Path configuration."""
    stories_dir: str = "stories"
    saves_dir: str = "saves"
    static_dir: str = "static"


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str = "INFO"
    file: Optional[str] = "wenyoo.log"


@dataclass
class FormConfig:
    """Form/Post feature configuration."""
    enabled: bool = True
    max_file_size_mb: float = 20.0  # Maximum file size for uploads
    max_text_length: int = 100000  # Maximum extracted text length
    allowed_file_types: list = field(default_factory=lambda: [
        "text/plain",
        "application/pdf",
        "text/markdown",
        "text/csv",
        "application/json"
    ])
    save_original_files: bool = False  # Whether to save original files to disk
    upload_dir: str = "data/uploads"  # Directory for saving files if enabled


@dataclass
class Config:
    """Main configuration container."""
    llm: LLMConfig = field(default_factory=LLMConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    forms: FormConfig = field(default_factory=FormConfig)
    
    def validate(self) -> None:
        """Validate all configuration sections."""
        self.llm.validate()


def _deep_merge(base: dict, override: dict) -> dict:
    """Deep merge two dictionaries, with override taking precedence."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _resolve_config_group(config_data: dict, config_group: Optional[str]) -> dict:
    """Merge shared config with a selected config group when configured."""
    groups = config_data.get(CONFIG_GROUPS_KEY)
    if groups is None:
        return config_data

    if not isinstance(groups, dict):
        raise ValueError(f"'{CONFIG_GROUPS_KEY}' must be a mapping of group names to config sections.")

    selected_group = config_group or "default"
    if "default" not in groups:
        raise ValueError(
            f"'{CONFIG_GROUPS_KEY}.default' is required when '{CONFIG_GROUPS_KEY}' is present."
        )
    if selected_group not in groups:
        available_groups = ", ".join(sorted(groups.keys()))
        raise ValueError(
            f"Unknown config group '{selected_group}'. "
            f"Available groups: {available_groups}"
        )

    shared_config = {
        key: value for key, value in config_data.items()
        if key != CONFIG_GROUPS_KEY
    }
    group_config = groups[selected_group]
    if not isinstance(group_config, dict):
        raise ValueError(
            f"'{CONFIG_GROUPS_KEY}.{selected_group}' must be a mapping of config sections."
        )
    return _deep_merge(shared_config, group_config)


def _dict_to_config(data: dict) -> Config:
    """Convert a dictionary to Config dataclass."""
    llm_data = data.get("llm", {})
    server_data = data.get("server", {})
    paths_data = data.get("paths", {})
    logging_data = data.get("logging", {})
    forms_data = data.get("forms", {})
    
    return Config(
        llm=LLMConfig(
            provider=llm_data.get("provider", "mock"),
            base_url=llm_data.get("base_url", "http://localhost:11434/v1"),
            model=llm_data.get("model", "llama3"),
            api_key_env=llm_data.get("api_key_env", "LLM_API_KEY"),
            timeout_connect=float(llm_data.get("timeout_connect", 30.0)),
            timeout_read=float(llm_data.get("timeout_read", 120.0)),
        ),
        server=ServerConfig(
            host=server_data.get("host", "127.0.0.1"),
            port=server_data.get("port", 8000),
            editor_secret=server_data.get("editor_secret"),
        ),
        paths=PathsConfig(
            stories_dir=paths_data.get("stories_dir", "stories"),
            saves_dir=paths_data.get("saves_dir", "saves"),
            static_dir=paths_data.get("static_dir", "static"),
        ),
        logging=LoggingConfig(
            level=logging_data.get("level", "INFO"),
            file=logging_data.get("file", "wenyoo.log"),
        ),
        forms=FormConfig(
            enabled=forms_data.get("enabled", True),
            max_file_size_mb=float(forms_data.get("max_file_size_mb", 20.0)),
            max_text_length=int(forms_data.get("max_text_length", 100000)),
            allowed_file_types=forms_data.get("allowed_file_types", [
                "text/plain", "application/pdf", "text/markdown", 
                "text/csv", "application/json"
            ]),
            save_original_files=forms_data.get("save_original_files", False),
            upload_dir=forms_data.get("upload_dir", "data/uploads"),
        ),
    )


def load_config(
    config_path: Optional[str] = None,
    env_file: Optional[str] = None,
    config_group: Optional[str] = None,
) -> Config:
    """
    Load configuration from file and environment.
    
    Args:
        config_path: Path to config.yaml file. If None, searches for config.yaml
                    in the current directory and project root.
        env_file: Path to .env file. If None, searches for .env in the current
                 directory and project root.
        config_group: Named config group to merge on top of shared config.
                     If omitted and config_groups exists, uses the 'default' group.
    
    Returns:
        Config object with all settings loaded.
    
    Raises:
        ValueError: If configuration is invalid.
        FileNotFoundError: If specified config file doesn't exist.
    """
    # Load .env file first (for API keys)
    _load_env_file(env_file)
    
    # Find and load config.yaml
    config_data = _load_config_file(config_path)

    # Merge the selected config group on top of shared config
    config_data = _resolve_config_group(config_data, config_group)
    
    # Apply environment variable overrides
    config_data = _apply_env_overrides(config_data)
    
    # Convert to Config object
    config = _dict_to_config(config_data)
    
    # Validate
    config.validate()
    
    return config


def _load_env_file(env_file: Optional[str] = None) -> None:
    """Load environment variables from .env file."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        logger.warning(
            "python-dotenv not installed. "
            "Install it with: pip install python-dotenv"
        )
        return
    
    # Search paths for .env
    search_paths = []
    if env_file:
        search_paths.append(Path(env_file))
    
    # Add common locations
    cwd = Path.cwd()
    search_paths.extend([
        cwd / ".env",
        cwd.parent / ".env",
        Path(__file__).parent.parent / ".env",  # Project root
    ])
    
    for path in search_paths:
        if path.exists():
            load_dotenv(path)
            logger.info(f"Loaded environment from: {path}")
            return
    
    logger.debug("No .env file found")


def _load_config_file(config_path: Optional[str] = None) -> dict:
    """Load configuration from YAML file."""
    # Search paths for config.yaml
    search_paths = []
    if config_path:
        search_paths.append(Path(config_path))
    
    # Add common locations
    cwd = Path.cwd()
    search_paths.extend([
        cwd / "config.yaml",
        cwd / "config.yml",
        cwd.parent / "config.yaml",
        Path(__file__).parent.parent / "config.yaml",  # Project root
    ])
    
    for path in search_paths:
        if path.exists():
            logger.info(f"Loading config from: {path}")
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
    
    # No config file found, use defaults
    logger.info("No config.yaml found, using default configuration")
    return {}


def _apply_env_overrides(config_data: dict) -> dict:
    """Apply environment variable overrides to config."""
    # Environment variable mappings
    # Format: ENV_VAR -> (section, key)
    env_mappings = {
        "LLM_PROVIDER": ("llm", "provider"),
        "LLM_BASE_URL": ("llm", "base_url"),
        "LLM_MODEL": ("llm", "model"),
        "LLM_API_KEY_ENV": ("llm", "api_key_env"),
        "SERVER_HOST": ("server", "host"),
        "SERVER_PORT": ("server", "port"),
        "EDITOR_SECRET": ("server", "editor_secret"),
        "STORIES_DIR": ("paths", "stories_dir"),
        "SAVES_DIR": ("paths", "saves_dir"),
        "STATIC_DIR": ("paths", "static_dir"),
        "LOG_LEVEL": ("logging", "level"),
        "LOG_FILE": ("logging", "file"),
    }
    
    for env_var, (section, key) in env_mappings.items():
        value = os.getenv(env_var)
        if value is not None:
            if section not in config_data:
                config_data[section] = {}
            
            # Type conversion for specific keys
            if key == "port":
                try:
                    value = int(value)
                except ValueError:
                    logger.warning(f"Invalid integer for {env_var}: {value!r}, ignoring")
                    continue
            
            config_data[section][key] = value
            logger.debug(f"Override from env: {section}.{key} = {value}")
    
    return config_data


# Convenience function for CLI argument overrides
def override_config(config: Config, **kwargs) -> Config:
    """
    Override config values from CLI arguments.
    
    Args:
        config: Base configuration
        **kwargs: Override values (e.g., host="127.0.0.1", port=9000)
    
    Returns:
        Updated Config object
    """
    # Map flat kwargs to nested config
    if "host" in kwargs and kwargs["host"] is not None:
        config.server.host = kwargs["host"]
    if "port" in kwargs and kwargs["port"] is not None:
        config.server.port = kwargs["port"]
    if "stories_dir" in kwargs and kwargs["stories_dir"] is not None:
        config.paths.stories_dir = kwargs["stories_dir"]
    if "saves_dir" in kwargs and kwargs["saves_dir"] is not None:
        config.paths.saves_dir = kwargs["saves_dir"]
    if "static_dir" in kwargs and kwargs["static_dir"] is not None:
        config.paths.static_dir = kwargs["static_dir"]
    if "log_level" in kwargs and kwargs["log_level"] is not None:
        config.logging.level = kwargs["log_level"]
    
    # LLM overrides
    if "llm_provider" in kwargs and kwargs["llm_provider"] is not None:
        config.llm.provider = kwargs["llm_provider"]
    if "llm_base_url" in kwargs and kwargs["llm_base_url"] is not None:
        config.llm.base_url = kwargs["llm_base_url"]
    if "llm_model" in kwargs and kwargs["llm_model"] is not None:
        config.llm.model = kwargs["llm_model"]
    
    # Re-validate after overrides
    config.validate()
    
    return config
