
"""
Main entry point for the AI Native game engine.

This module initializes all components and starts the game engine.
"""
import os
import sys
import logging
import argparse

from typing import Dict, Any, Optional

from src.config import load_config, override_config, Config
from src.core.game_kernel import GameKernel
from src.core.story_manager import StoryManager
from src.core.state_manager import StateManager
from src.adapters.ollama_adapter import OllamaAdapter
from src.adapters.base_llm_adapter import BaseLLMAdapter
from src.adapters.claude_adapter import ClaudeAdapter
from src.adapters.mock_llm_adapter import MockLLMAdapter
from src.adapters.web_frontend_adapter import WebFrontendAdapter

logger = logging.getLogger(__name__)


# Set up logging
def setup_logging(log_level: str = "INFO") -> None:
    """Set up logging configuration.
    
    Args:
        log_level (str, optional): Logging level. Defaults to "INFO".
    """
    numeric_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"Invalid log level: {log_level}")
    
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler("wenyoo.log")
        ]
    )


# Parse command line arguments
def parse_args() -> argparse.Namespace:
    """Parse command line arguments.
    
    CLI arguments override values from config.yaml.
    
    Returns:
        argparse.Namespace: Parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description="Wenyoo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Configuration:
  The engine loads configuration from config.yaml and .env files.
  CLI arguments override config file values.
  
  See config.example.yaml for all configuration options.

Examples:
  python -m src.main                          # Use config.yaml settings
  python -m src.main --config-group claude    # Use the named config group
  python -m src.main --port 9000              # Override port
  python -m src.main --llm-provider mock      # Use mock LLM for testing
  python -m src.main --config my-config.yaml  # Use custom config file
        """
    )
    
    # Config file
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to config.yaml file (default: auto-detect)"
    )
    parser.add_argument(
        "--config-group",
        type=str,
        default=None,
        help="Named config group to load from config_groups (default: default)"
    )
    
    # Server overrides
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="Host to bind to (overrides config)"
    )
    
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port to bind to (overrides config)"
    )
    
    # LLM overrides
    parser.add_argument(
        "--llm-provider",
        type=str,
        default=None,
        choices=["openai-compatible", "ollama", "claude", "mock"],
        help="LLM provider type (overrides config)"
    )
    
    parser.add_argument(
        "--llm-base-url",
        type=str,
        default=None,
        help="LLM API base URL (overrides config)"
    )
    
    parser.add_argument(
        "--llm-model",
        type=str,
        default=None,
        help="LLM model name (overrides config)"
    )
    
    # Path overrides
    parser.add_argument(
        "--stories-dir",
        type=str,
        default=None,
        help="Directory containing story files (overrides config)"
    )
    
    parser.add_argument(
        "--saves-dir",
        type=str,
        default=None,
        help="Directory for saved games (overrides config)"
    )
    
    parser.add_argument(
        "--static-dir",
        type=str,
        default=None,
        help="Directory for static web files (overrides config)"
    )
    
    # Logging
    parser.add_argument(
        "--log-level",
        type=str,
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level (overrides config)"
    )
    
    return parser.parse_args()


def create_llm_provider(config: Config):
    """Create LLM provider based on configuration.
    
    Args:
        config: Application configuration
        
    Returns:
        LLM provider instance
    """
    provider_type = config.llm.provider
    
    if provider_type == "mock":
        logger.info("Using MockLLMAdapter (no API calls)")
        return MockLLMAdapter()
    
    elif provider_type == "openai-compatible":
        logger.info(
            f"Using OpenAI-compatible LLM: {config.llm.base_url} "
            f"with model {config.llm.model}"
        )
        return BaseLLMAdapter(
            api_key=config.llm.api_key,
            base_url=config.llm.base_url,
            model=config.llm.model,
            timeout_connect=config.llm.timeout_connect,
            timeout_read=config.llm.timeout_read
        )
    
    elif provider_type == "claude":
        api_key = os.getenv("CLAUDE_API_KEY")
        if not api_key:
            api_key = config.llm.api_key
        if not api_key:
            raise ValueError(
                "API key required for Claude provider. "
                "Set CLAUDE_API_KEY or the configured api_key_env variable."
            )
        model = config.llm.model
        if model in ("llama3", "qwen-plus-latest"):
            model = "claude-sonnet-4-6"
        logger.info(f"Using Claude with model {model}")
        return ClaudeAdapter(
            api_key=api_key,
            model=model,
            timeout_connect=config.llm.timeout_connect,
            timeout_read=config.llm.timeout_read,
        )

    elif provider_type == "ollama":
        logger.info(
            f"Using Ollama: {config.llm.base_url} "
            f"with model {config.llm.model}"
        )
        return OllamaAdapter(
            base_url=config.llm.base_url,
            model=config.llm.model,
            timeout_connect=config.llm.timeout_connect,
            timeout_read=config.llm.timeout_read
        )
    
    else:
        raise ValueError(f"Unknown LLM provider: {provider_type}")


# Main function
async def main() -> None:
    """Main entry point."""
    # Parse arguments
    args = parse_args()
    
    # Load configuration
    try:
        config = load_config(config_path=args.config, config_group=args.config_group)
    except ValueError as e:
        print(f"Configuration error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Failed to load configuration: {e}")
        sys.exit(1)
    
    # Apply CLI overrides
    config = override_config(
        config,
        host=args.host,
        port=args.port,
        stories_dir=args.stories_dir,
        saves_dir=args.saves_dir,
        static_dir=args.static_dir,
        log_level=args.log_level,
        llm_provider=args.llm_provider,
        llm_base_url=args.llm_base_url,
        llm_model=args.llm_model,
    )
    
    # Set up logging
    setup_logging(config.logging.level)
    
    logger.info(f"Configuration loaded: LLM provider={config.llm.provider}, "
                f"model={config.llm.model}")
    
    # Initialize core components
    story_manager = StoryManager(stories_dir=config.paths.stories_dir)
    state_manager = StateManager(save_dir=config.paths.saves_dir)
    
    # Create LLM provider based on config
    try:
        llm_provider = create_llm_provider(config)
    except ValueError as e:
        print(f"LLM configuration error: {e}")
        sys.exit(1)
    
    # Initialize game kernel with core dependencies
    game_kernel = GameKernel(
        story_manager=story_manager,
        state_manager=state_manager,
        llm_provider=llm_provider
    )

    # Create web frontend adapter
    frontend_adapter = WebFrontendAdapter(
        host=config.server.host,
        port=config.server.port,
        static_dir=config.paths.static_dir,
        game_kernel=game_kernel,
        story_manager=story_manager,
        editor_secret=config.server.editor_secret,
    )
    
    # Set frontend adapter reference in game kernel
    game_kernel.frontend_adapter = frontend_adapter
    
    # Register frontend adapter as observer of game kernel
    game_kernel.register_observer(frontend_adapter)
    
    # Start web interface
    logger.info(f"Starting web interface on {config.server.host}:{config.server.port}...")
    await frontend_adapter.start()


if __name__ == "__main__":
    import asyncio
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nServer stopped by user.")
    except asyncio.CancelledError:
        pass  # Suppress asyncio cancellation traceback for graceful shutdown
