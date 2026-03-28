"""
Story manager component for discovering and loading stories.
"""
import logging
import os
import yaml
from typing import List, Dict, Any, Optional

from src.models.story_models import Story, load_story_from_file

class StoryManager:
    """
    Manages story discovery and loading.
    """
    
    def __init__(self, stories_dir: str):
        """
        Initialize the story manager.
        
        Args:
            stories_dir: Directory containing story files
        """
        self.stories_dir = stories_dir
        self.logger = logging.getLogger(__name__)
        self._stories: Optional[List[Dict[str, Any]]] = None
        self.logger.info(f"Story manager initialized with stories directory: {stories_dir}")
    
    def discover_stories(self) -> List[Dict[str, Any]]:
        """
        Discover available stories in the stories directory.
        Supports both single YAML files and story folders (with main.yaml).
        
        Returns:
            List of story metadata dictionaries
        """
        if self._stories is not None:
            return self._stories

        stories = []
        
        if not os.path.exists(self.stories_dir):
            self.logger.warning(f"Stories directory does not exist: {self.stories_dir}")
            return stories
        
        self.logger.info(f"Scanning stories directory: {self.stories_dir}")
        
        for entry in os.listdir(self.stories_dir):
            entry_path = os.path.join(self.stories_dir, entry)
            
            # Check for story folders (containing main.yaml)
            if os.path.isdir(entry_path):
                main_yaml = os.path.join(entry_path, 'main.yaml')
                main_yml = os.path.join(entry_path, 'main.yml')
                
                if os.path.exists(main_yaml):
                    file_path = main_yaml
                elif os.path.exists(main_yml):
                    file_path = main_yml
                else:
                    continue  # Not a story folder
                    
                try:
                    self.logger.debug(f"Loading story folder from {file_path}")
                    
                    with open(file_path, 'r', encoding='utf-8') as file:
                        story_data = yaml.safe_load(file)
                        
                    if not story_data.get('id') or not story_data.get('title'):
                        self.logger.warning(f"Story folder {entry} missing required fields (id/title)")
                        continue
                        
                    stories.append({
                        "id": story_data.get('id', entry),
                        "name": story_data.get('name', story_data.get('title', 'Unnamed Story')),
                        "title": story_data.get('title', story_data.get('name', 'Unnamed Story')),
                        "author": story_data.get('author', 'Unknown'),
                        "version": story_data.get('version', '1.0'),
                        "description": story_data.get('description', ''),
                        "file_path": file_path
                    })
                except Exception as e:
                    self.logger.error(f"Error loading story folder {entry}: {e}")
                    
            # Check for single YAML files
            elif (entry.endswith('.yaml') or entry.endswith('.yml')) and not entry.endswith('.template.yaml'):
                try:
                    file_path = entry_path
                    self.logger.debug(f"Loading story from {file_path}")
                    
                    with open(file_path, 'r', encoding='utf-8') as file:
                        story_data = yaml.safe_load(file)
                        
                    if not story_data.get('id') or not story_data.get('title'):
                        self.logger.warning(f"Story {entry} missing required fields (id/title)")
                        continue
                        
                    stories.append({
                        "id": story_data.get('id', os.path.splitext(entry)[0]),
                        "name": story_data.get('name', story_data.get('title', 'Unnamed Story')),
                        "title": story_data.get('title', story_data.get('name', 'Unnamed Story')),
                        "author": story_data.get('author', 'Unknown'),
                        "version": story_data.get('version', '1.0'),
                        "description": story_data.get('description', ''),
                        "file_path": file_path
                    })
                except Exception as e:
                    self.logger.error(f"Error loading story from {entry}: {e}")
        
        self.logger.info(f"Found {len(stories)} valid stories")
        self._stories = stories
        return self._stories

    def invalidate_cache(self):
        """
        Invalidate the internal cache of stories and templates.
        This forces the next call to discover_stories to rescan the directory.
        """
        self._stories = None
        self.logger.info("Story manager cache invalidated")
    
    def load_story(self, story_id: str) -> Optional[Story]:
        """
        Load a story by ID, processing any dynamic elements.
        
        Args:
            story_id: ID of the story to load
            
        Returns:
            The loaded and processed story or None if not found
        """
        stories = self.discover_stories()
        for story_meta in stories:
            if story_meta['id'] == story_id:
                try:
                    file_path = story_meta['file_path']
                    story = load_story_from_file(file_path)
                    self.logger.info(f"Successfully loaded story: {story.name}")
                    return story
                except Exception as e:
                    self.logger.error(f"Error loading story {story_id} from file {story_meta['file_path']}: {e}", exc_info=True)
                    return None
        self.logger.warning(f"Story not found: {story_id}")
        return None

    def get_story_path(self, story_id: str) -> Optional[str]:
        """
        Get the file path for a story by ID.
        
        Args:
            story_id: ID of the story
            
        Returns:
            The file path or None if not found
        """
        stories = self.discover_stories()
        for story_meta in stories:
            if story_meta['id'] == story_id:
                return story_meta['file_path']
        return None
