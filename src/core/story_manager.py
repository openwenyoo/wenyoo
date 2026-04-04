"""
Story manager component for discovering and loading stories.
"""
import logging
import os
import yaml
from pathlib import Path
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

    def _build_frontend_metadata(
        self,
        story_id: str,
        story_data: Dict[str, Any],
        story_root: str,
    ) -> Optional[Dict[str, Any]]:
        frontend = story_data.get("frontend") or {}
        app = frontend.get("app") if isinstance(frontend, dict) else None
        if not isinstance(app, dict):
            return None

        mode = app.get("mode", "sandboxed_app")
        app_root = app.get("app_root", "frontend")
        entry = app.get("entry", "index.html")
        client_type = app.get("client_type", "story_app")
        sandbox = app.get("sandbox") or ["allow-scripts", "allow-same-origin"]
        capabilities = app.get("capabilities") or []

        app_root_path = Path(story_root) / app_root
        entry_path = app_root_path / entry
        if not entry_path.exists():
            self.logger.warning(
                "Story '%s' declares frontend app entry '%s' but file does not exist.",
                story_id,
                entry_path,
            )
            return None

        return {
            "app": {
                "mode": mode,
                "app_root": app_root,
                "entry": entry,
                "entry_url": f"/story-apps/{story_id}/{entry}",
                "client_type": client_type,
                "sandbox": list(sandbox),
                "capabilities": list(capabilities),
            }
        }
    
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
                        
                    story_id = story_data.get('id', entry)
                    stories.append({
                        "id": story_id,
                        "name": story_data.get('name', story_data.get('title', 'Unnamed Story')),
                        "title": story_data.get('title', story_data.get('name', 'Unnamed Story')),
                        "author": story_data.get('author', 'Unknown'),
                        "version": story_data.get('version', '1.0'),
                        "description": story_data.get('description', ''),
                        "file_path": file_path,
                        "story_root": entry_path,
                        "frontend": self._build_frontend_metadata(story_id, story_data, entry_path),
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
                        
                    story_id = story_data.get('id', os.path.splitext(entry)[0])
                    stories.append({
                        "id": story_id,
                        "name": story_data.get('name', story_data.get('title', 'Unnamed Story')),
                        "title": story_data.get('title', story_data.get('name', 'Unnamed Story')),
                        "author": story_data.get('author', 'Unknown'),
                        "version": story_data.get('version', '1.0'),
                        "description": story_data.get('description', ''),
                        "file_path": file_path,
                        "story_root": os.path.dirname(file_path),
                        "frontend": self._build_frontend_metadata(story_id, story_data, os.path.dirname(file_path)),
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

    def get_story_metadata(self, story_id: str) -> Optional[Dict[str, Any]]:
        """Get cached discovery metadata for a story."""
        stories = self.discover_stories()
        for story_meta in stories:
            if story_meta["id"] == story_id:
                return story_meta
        return None

    def get_story_root(self, story_id: str) -> Optional[str]:
        metadata = self.get_story_metadata(story_id)
        if not metadata:
            return None
        return metadata.get("story_root")

    def resolve_story_frontend_asset(self, story_id: str, asset_path: str) -> Optional[str]:
        """Resolve a frontend asset declared by a story to a safe absolute path."""
        metadata = self.get_story_metadata(story_id)
        frontend = metadata.get("frontend") if metadata else None
        app = frontend.get("app") if isinstance(frontend, dict) else None
        story_root = metadata.get("story_root") if metadata else None
        if not app or not story_root:
            return None

        app_root = app.get("app_root", "frontend")
        base_dir = os.path.realpath(os.path.join(story_root, app_root))
        target_path = os.path.realpath(os.path.join(base_dir, asset_path or app.get("entry", "index.html")))
        try:
            if os.path.commonpath([target_path, base_dir]) != base_dir:
                return None
        except ValueError:
            return None
        if not os.path.exists(target_path) or not os.path.isfile(target_path):
            return None
        return target_path
