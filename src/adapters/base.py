from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, Callable, TYPE_CHECKING
import asyncio

if TYPE_CHECKING:
    from src.core.game_kernel import GameKernel

class FrontendAdapter(ABC):
    """Abstract base class for frontend adapters."""
    
    def __init__(self, game_kernel: Optional['GameKernel'] = None):
        """Initialize the frontend adapter.

        Args:
            game_kernel: Reference to the game kernel (optional for deferred initialization)
        """
        self.game_kernel = game_kernel
        self._observers = set()
    
    @abstractmethod
    async def start(self) -> None:
        """Start the frontend interface."""
        pass
    
    @abstractmethod
    async def update_display(self, game_state: Dict[str, Any]) -> bool:
        """Update the display with current game state.

        Args:
            game_state: Current game state dictionary
            
        Returns:
            bool: True if update was successful
        """
        pass
    
    @abstractmethod
    async def send_response(self, response: Dict[str, Any]) -> bool:
        """Send a response to the frontend.
        
        Args:
            response: The response to send
            
        Returns:
            bool: True if response was sent successfully
        """
        pass
    
    @abstractmethod
    async def notify_error(self, error: str) -> None:
        """Notify the frontend of an error.
        
        Args:
            error: The error message
        """
        pass
    
    def format_for_client(self, text: str, client_type: str = 'web') -> str:
        """Convert abstract game tokens in text to client-specific markup.

        This is the centralized place for ALL client-specific text formatting.
        Subclasses should override to support their client formats.

        The engine produces neutral ``[[type:id|display_text]]`` tokens.
        This method converts them into the markup expected by the target client.

        Args:
            text: Text potentially containing abstract link tokens.
            client_type: The target client type (e.g. 'web').

        Returns:
            Text with abstract tokens replaced by client-specific markup.
        """
        return text

    def _format_game_state_for_player(self, game_state_dict: dict, player_id: str) -> dict:
        """Format all text fields in a game state dict for a specific player's client.

        Args:
            game_state_dict: The game state dict built by ``build_game_state_dict``.
            player_id: The player's ID (used to look up client_type).

        Returns:
            The same dict with text fields formatted for the player's client.
        """
        client_type = self.player_sessions.get(player_id, {}).get('client_type', 'web')
        for node_data in game_state_dict.get('nodes', {}).values():
            if 'processed_description' in node_data:
                node_data['processed_description'] = self.format_for_client(
                    node_data['processed_description'], client_type
                )
        return game_state_dict

    async def on_game_start(self, player_name: str) -> bool:
        """Notify the frontend that a new game has started.
        
        Args:
            player_name: Name of the player starting the game
            
        Returns:
            bool: True if notification was sent successfully
        """
        return True
    
    def update(self, state: Dict[str, Any]) -> None:
        """Observer pattern update method (synchronous wrapper).
        
        Args:
            state: The new game state
        """
        try:
            loop = asyncio.get_running_loop()
            asyncio.create_task(self.update_display(state))
        except RuntimeError:
            # No running loop - this is called from sync context
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.update_display(state))
            loop.close()