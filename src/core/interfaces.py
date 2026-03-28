"""
Interfaces for the AI Native game engine.

This module defines the interfaces that different components of the game engine
will implement, ensuring a consistent API across different implementations.
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any


class ILLMProvider(ABC):
    """Interface for language model providers."""
    
    @abstractmethod
    async def generate_response(self, prompt: str, **kwargs) -> str:
        """Generate a structured response from a prompt.
        
        Args:
            prompt (str): The prompt to generate a response for.
            **kwargs: Provider-specific generation options.
            
        Returns:
            str: The generated response.
        """
        pass
    
    @abstractmethod
    async def generate_text_response(self, prompt: str, system_prompt: Optional[str] = None, **kwargs) -> str:
        """Generate a plain-text response from a prompt.
        
        Args:
            prompt (str): The prompt to generate a response for.
            system_prompt (Optional[str]): Optional system prompt.
            **kwargs: Provider-specific generation options.
            
        Returns:
            str: The generated response.
        """
        pass


class IStateManager(ABC):
    """Interface for state management."""
    
    @abstractmethod
    def save_state(self, state: Dict[str, Any]) -> bool:
        """Save the current game state.
        
        Args:
            state (Dict[str, Any]): The game state to save.
            
        Returns:
            bool: True if the state was saved successfully, False otherwise.
        """
        pass
    
    @abstractmethod
    def load_state(self, state_id: str) -> Optional[Dict[str, Any]]:
        """Load a game state by ID.
        
        Args:
            state_id (str): The ID of the state to load.
            
        Returns:
            Optional[Dict[str, Any]]: The loaded game state, or None if not found.
        """
        pass
    
    @abstractmethod
    def update_state(self, state_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update a game state with new values.
        
        Args:
            state_id (str): The ID of the state to update.
            updates (Dict[str, Any]): The updates to apply.
            
        Returns:
            Optional[Dict[str, Any]]: The updated game state, or None if not found.
        """
        pass
    
    @abstractmethod
    def list_saved_states(self) -> List[Dict[str, Any]]:
        """List all saved game states.
        
        Returns:
            List[Dict[str, Any]]: A list of saved game states metadata.
        """
        pass
    
    @abstractmethod
    def delete_state(self, state_id: str) -> bool:
        """Delete a saved game state.
        
        Args:
            state_id (str): The ID of the state to delete.
            
        Returns:
            bool: True if the state was deleted successfully, False otherwise.
        """
        pass


class IFrontendAdapter(ABC):
    """Interface for frontend adapters."""
    
    @abstractmethod
    def send_response(self, response: Dict[str, Any]) -> bool:
        """Send a response to the frontend.
        
        Args:
            response (Dict[str, Any]): The response to send.
            
        Returns:
            bool: True if the response was sent successfully, False otherwise.
        """
        pass
    
    @abstractmethod
    def receive_input(self) -> Optional[Dict[str, Any]]:
        """Receive input from the frontend.
        
        Returns:
            Optional[Dict[str, Any]]: The received input, or None if no input is available.
        """
        pass
    
    @abstractmethod
    def update_display(self, state: Dict[str, Any]) -> bool:
        """Update the frontend display with the current state.
        
        Args:
            state (Dict[str, Any]): The current game state.
            
        Returns:
            bool: True if the display was updated successfully, False otherwise.
        """
        pass
    
    @abstractmethod
    async def notify_error(self, error: str) -> None:
        """Notify the frontend of an error.
        
        Args:
            error (str): The error message.
        """
        pass


class IStoryProvider(ABC):
    """Interface for story providers."""
    
    @abstractmethod
    def get_story(self, story_id: str) -> Optional[Dict[str, Any]]:
        """Get a story by ID.
        
        Args:
            story_id (str): The ID of the story.
            
        Returns:
            Optional[Dict[str, Any]]: The story, or None if not found.
        """
        pass
    
    @abstractmethod
    def list_stories(self) -> List[Dict[str, Any]]:
        """List all available stories.
        
        Returns:
            List[Dict[str, Any]]: A list of story metadata.
        """
        pass
    
    @abstractmethod
    def create_story(self, story_data: Dict[str, Any]) -> Optional[str]:
        """Create a new story.
        
        Args:
            story_data (Dict[str, Any]): The story data.
            
        Returns:
            Optional[str]: The ID of the created story, or None if creation failed.
        """
        pass
    
    @abstractmethod
    def update_story(self, story_id: str, updates: Dict[str, Any]) -> bool:
        """Update an existing story.
        
        Args:
            story_id (str): The ID of the story to update.
            updates (Dict[str, Any]): The updates to apply.
            
        Returns:
            bool: True if the story was updated successfully, False otherwise.
        """
        pass
    
    @abstractmethod
    def delete_story(self, story_id: str) -> bool:
        """Delete a story.
        
        Args:
            story_id (str): The ID of the story to delete.
            
        Returns:
            bool: True if the story was deleted successfully, False otherwise.
        """
        pass


class IEntityProvider(ABC):
    """Interface for entity providers."""
    
    @abstractmethod
    def get_item(self, item_id: str) -> Optional[Dict[str, Any]]:
        """Get an item by ID.
        
        Args:
            item_id (str): The ID of the item.
            
        Returns:
            Optional[Dict[str, Any]]: The item, or None if not found.
        """
        pass
    
    @abstractmethod
    def get_character(self, character_id: str) -> Optional[Dict[str, Any]]:
        """Get a character by ID.
        
        Args:
            character_id (str): The ID of the character.
            
        Returns:
            Optional[Dict[str, Any]]: The character, or None if not found.
        """
        pass
    
    @abstractmethod
    def get_location(self, location_id: str) -> Optional[Dict[str, Any]]:
        """Get a location by ID.
        
        Args:
            location_id (str): The ID of the location.
            
        Returns:
            Optional[Dict[str, Any]]: The location, or None if not found.
        """
        pass