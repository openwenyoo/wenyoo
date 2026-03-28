"""
Input Parser for the AI Native game engine.

This module parses player input to identify character mentions (@character)
and determine the type of interaction (talk to, act on, etc.).
"""
import re
import logging
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)


@dataclass
class ParsedInput:
    """Result of parsing player input."""
    input_type: str  # "character_interaction", "object_action", "navigation", "other"
    character_id: Optional[str] = None  # Resolved character ID
    character_name: Optional[str] = None  # Original character name/id from input
    action_keyword: Optional[str] = None  # For "trade @hermit" → "trade"
    message: Optional[str] = None  # For "@hermit hello" → "hello"
    raw_input: str = ""
    is_trigger: bool = False  # True if this is from a system trigger, not player input
    target_type: Optional[str] = None  # For compatibility with effect triggers
    target_id: Optional[str] = None  # For compatibility with effect triggers
    
    def is_character_interaction(self) -> bool:
        return self.input_type == "character_interaction"


class InputParser:
    """
    Parses player input to identify @ mentions and interaction types.
    
    Supported patterns:
    - "@character message" → Talk to character (message is what player says)
    - "action @character" → Perform action on character
    - "action @character extra" → Perform action on character with extra context
    - "give item @character" → Give item to character
    
    Examples:
    - "@hermit hello" → character_interaction, character="hermit", message="hello"
    - "trade @hermit" → character_interaction, character="hermit", action_keyword="trade"
    - "hit @goblin" → character_interaction, character="goblin", action_keyword="hit"
    - "@monkey hi" → character_interaction, character="monkey", message="hi"
    """
    
    # Pattern: @character_name [,|:] message (talk to character)
    # Supports alphanumeric, underscores, and Chinese characters
    # Support for optional comma/colon after mention: @hermit, hello
    MENTION_FIRST_PATTERN = re.compile(
        r'^@([\w\u4e00-\u9fff]+)(?:[，,：:]\s*|\s+)(.+)$',
        re.UNICODE
    )
    
    # Pattern: action @character_name [extra]
    ACTION_ON_PATTERN = re.compile(
        r'^([\w\u4e00-\u9fff]+)\s+@([\w\u4e00-\u9fff]+)(?:(?:[，,：:]\s*|\s+)(.*))?$',
        re.UNICODE
    )
    
    # Pattern: give item @character
    GIVE_PATTERN = re.compile(
        r'^(?:give)\s+([\w\u4e00-\u9fff]+)\s+@([\w\u4e00-\u9fff]+)$',
        re.UNICODE | re.IGNORECASE
    )

    # Pattern: just @character_name
    SINGLE_MENTION_PATTERN = re.compile(
        r'^@([\w\u4e00-\u9fff]+)$',
        re.UNICODE
    )
    
    def __init__(self):
        self._character_name_map: Dict[str, str] = {}  # name -> id mapping
    
    def set_available_characters(self, characters: List[Any]) -> None:
        """
        Set the available characters for name resolution.
        
        Args:
            characters: List of Character objects with id and name attributes
        """
        self._character_name_map.clear()
        for char in characters:
            char_id = char.id if hasattr(char, 'id') else str(char.get('id', ''))
            char_name = char.name if hasattr(char, 'name') else str(char.get('name', ''))
            
            # Map both ID and name to the ID
            self._character_name_map[char_id.lower()] = char_id
            self._character_name_map[char_name.lower()] = char_id
            
            # Also map without spaces/underscores for flexibility
            simplified_id = char_id.lower().replace('_', '').replace(' ', '')
            simplified_name = char_name.lower().replace('_', '').replace(' ', '')
            self._character_name_map[simplified_id] = char_id
            self._character_name_map[simplified_name] = char_id
            
            # Add common short names/aliases
            # E.g., "forest_hermit" -> "hermit", "clever_monkey" -> "monkey"
            if len(char_name) >= 2:
                # Map last 2 characters (for shorter aliases)
                short_name = char_name[-2:]
                self._character_name_map[short_name.lower()] = char_id
                
                # Also try first 2 characters
                first_part = char_name[:2]
                self._character_name_map[first_part.lower()] = char_id
    
    def _resolve_character(self, name_or_id: str) -> Optional[str]:
        """
        Resolve a character name/id to the actual character ID.
        
        Args:
            name_or_id: The character name or ID from user input
            
        Returns:
            The resolved character ID, or None if not found
        """
        if not name_or_id:
            return None
        
        lookup = name_or_id.lower().replace('_', '').replace(' ', '')
        return self._character_name_map.get(lookup)
    
    def parse(self, input_text: str) -> ParsedInput:
        """
        Parse player input to identify character interactions.
        
        Args:
            input_text: The raw player input
            
        Returns:
            ParsedInput with identified interaction type and details
        """
        if not input_text:
            return ParsedInput(input_type="other", raw_input="")
        
        input_text = input_text.strip()
        
        # Try "give item @character" pattern first
        match = self.GIVE_PATTERN.match(input_text)
        if match:
            item, char_name = match.groups()
            char_id = self._resolve_character(char_name)
            if char_id:
                logger.debug(f"Parsed give pattern: item={item}, character={char_id}")
                return ParsedInput(
                    input_type="character_interaction",
                    character_id=char_id,
                    character_name=char_name,
                    action_keyword="give",
                    message=item,
                    raw_input=input_text
                )
        
        # Try "action @character [extra]" pattern
        match = self.ACTION_ON_PATTERN.match(input_text)
        if match:
            action, char_name, extra = match.groups()
            char_id = self._resolve_character(char_name)
            if char_id:
                logger.debug(f"Parsed action pattern: action={action}, character={char_id}, extra={extra}")
                return ParsedInput(
                    input_type="character_interaction",
                    character_id=char_id,
                    character_name=char_name,
                    action_keyword=action.lower(),
                    message=extra,
                    raw_input=input_text
                )
        
        # Try "@character message" pattern
        match = self.MENTION_FIRST_PATTERN.match(input_text)
        if match:
            char_name, message = match.groups()
            char_id = self._resolve_character(char_name)
            if char_id:
                logger.debug(f"Parsed mention pattern: character={char_id}, message={message}")
                return ParsedInput(
                    input_type="character_interaction",
                    character_id=char_id,
                    character_name=char_name,
                    message=message.strip(),
                    raw_input=input_text
                )
        
        # Try just "@character" pattern
        match = self.SINGLE_MENTION_PATTERN.match(input_text)
        if match:
            char_name = match.group(1)
            char_id = self._resolve_character(char_name)
            if char_id:
                logger.debug(f"Parsed single mention pattern: character={char_id}")
                return ParsedInput(
                    input_type="character_interaction",
                    character_id=char_id,
                    character_name=char_name,
                    raw_input=input_text
                )
        
        # No character interaction pattern matched
        logger.debug(f"No character pattern matched for: {input_text}")
        return ParsedInput(
            input_type="other",
            raw_input=input_text
        )
    
    def extract_all_mentions(self, input_text: str) -> List[str]:
        """
        Extract all @mentions from input text.
        
        Args:
            input_text: The raw player input
            
        Returns:
            List of mentioned character names/IDs
        """
        pattern = re.compile(r'@([\w\u4e00-\u9fff]+)', re.UNICODE)
        matches = pattern.findall(input_text)
        return [self._resolve_character(m) or m for m in matches]

