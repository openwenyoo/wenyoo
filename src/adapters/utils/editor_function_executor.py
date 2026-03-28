"""Execute editor tool functions and track changes for SSE streaming.

This module handles the execution of AI tool calls and generates
Server-Sent Events (SSE) for real-time updates in the editor frontend.
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
import json
import logging
import time

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """SSE event types for editor updates."""
    THINKING = "thinking"
    FUNCTION_CALL = "function_call"
    # Node events
    NODE_CREATED = "node_created"
    NODE_UPDATED = "node_updated"
    NODE_DELETED = "node_deleted"
    EDGE_CREATED = "edge_created"
    EDGE_DELETED = "edge_deleted"
    OBJECT_ADDED = "object_added"
    # Character events
    CHARACTER_CREATED = "character_created"
    CHARACTER_UPDATED = "character_updated"
    CHARACTER_DELETED = "character_deleted"
    # Global object events
    GLOBAL_OBJECT_CREATED = "global_object_created"
    GLOBAL_OBJECT_UPDATED = "global_object_updated"
    GLOBAL_OBJECT_DELETED = "global_object_deleted"
    # Parameter events
    PARAMETER_SET = "parameter_set"
    PARAMETER_DELETED = "parameter_deleted"
    # General
    ERROR = "error"
    COMPLETE = "complete"


@dataclass
class SSEEvent:
    """Server-Sent Event for streaming to frontend."""
    event_type: EventType
    data: Dict[str, Any]
    
    def to_sse(self) -> str:
        """Format as SSE string for streaming response."""
        return f"event: {self.event_type.value}\ndata: {json.dumps(self.data, ensure_ascii=False)}\n\n"


@dataclass
class ChangeRecord:
    """Record of a single change made during the session."""
    change_type: str  # create, update, delete, add_action, add_object
    node_id: str
    timestamp: float = field(default_factory=time.time)
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EditorState:
    """Mutable state for the editor session."""
    nodes: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    edges: List[Dict[str, Any]] = field(default_factory=list)
    characters: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    objects: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    parameters: Dict[str, Any] = field(default_factory=dict)
    changes: List[ChangeRecord] = field(default_factory=list)
    
    @classmethod
    def from_frontend(cls, nodes: List[Dict] = None, edges: List[Dict] = None,
                      characters: List[Dict] = None, objects: List[Dict] = None,
                      parameters: Dict[str, Any] = None) -> 'EditorState':
        """Create state from frontend data.
        
        Args:
            nodes: List of ReactFlow node objects with 'id' and 'data' fields
            edges: List of edge objects with 'source', 'target', 'label' fields
            characters: List of character objects
            objects: List of global object definitions
            parameters: Dict of initial_variables
            
        Returns:
            EditorState instance
        """
        # Extract node data
        nodes_dict = {}
        for n in (nodes or []):
            node_id = n.get('id')
            if node_id:
                node_data = n.get('data', n)
                if 'id' not in node_data:
                    node_data = {**node_data, 'id': node_id}
                nodes_dict[node_id] = node_data
        
        # Extract characters
        chars_dict = {}
        for c in (characters or []):
            char_id = c.get('id')
            if char_id:
                chars_dict[char_id] = c
        
        # Extract objects
        objs_dict = {}
        for o in (objects or []):
            obj_id = o.get('id')
            if obj_id:
                objs_dict[obj_id] = o
        
        return cls(
            nodes=nodes_dict,
            edges=[e.copy() for e in (edges or [])],
            characters=chars_dict,
            objects=objs_dict,
            parameters=dict(parameters or {})
        )
    
    def add_change(self, change_type: str, entity_id: str, entity_type: str = "node", **details):
        """Record a change."""
        self.changes.append(ChangeRecord(
            change_type=change_type,
            node_id=entity_id,  # Keeping field name for compatibility
            details={"entity_type": entity_type, **details}
        ))


class EditorFunctionExecutor:
    """Execute editor tool functions and generate SSE events.
    
    This class maintains the state of the editor during an AI session
    and generates events for each change that can be streamed to the frontend.
    Supports nodes, characters, objects, and parameters.
    """
    
    def __init__(self, initial_nodes: List[Dict] = None, initial_edges: List[Dict] = None,
                 initial_characters: List[Dict] = None, initial_objects: List[Dict] = None,
                 initial_parameters: Dict[str, Any] = None):
        """Initialize executor with current editor state.
        
        Args:
            initial_nodes: Current nodes from ReactFlow
            initial_edges: Current edges from ReactFlow
            initial_characters: Current characters list
            initial_objects: Current global objects list
            initial_parameters: Current parameters/initial_variables dict
        """
        self.state = EditorState.from_frontend(
            nodes=initial_nodes or [],
            edges=initial_edges or [],
            characters=initial_characters or [],
            objects=initial_objects or [],
            parameters=initial_parameters or {}
        )
        self.events: List[SSEEvent] = []
        self._edge_id_counter = int(time.time() * 1000)
    
    def _generate_edge_id(self, source: str, target: str) -> str:
        """Generate a unique edge ID."""
        self._edge_id_counter += 1
        return f"ai-edge-{source}-{target}-{self._edge_id_counter}"
    
    def execute(self, function_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool function and return result.
        
        Args:
            function_name: Name of the tool function to execute
            arguments: Arguments passed to the function
            
        Returns:
            Result dictionary with success/error information
        """
        # Log the function call event
        self.events.append(SSEEvent(
            event_type=EventType.FUNCTION_CALL,
            data={
                "function": function_name,
                "arguments": arguments,
                "timestamp": time.time()
            }
        ))
        
        try:
            # Dispatch to appropriate handler
            handlers = {
                # Node handlers
                "create_node": self._create_node,
                "update_node": self._update_node,
                "add_action_to_node": self._add_action_to_node,
                "add_object_to_node": self._add_object_to_node,
                "delete_node": self._delete_node,
                "get_node": self._get_node,
                "list_nodes": self._list_nodes,
                # Character handlers
                "create_character": self._create_character,
                "update_character": self._update_character,
                "delete_character": self._delete_character,
                "get_character": self._get_character,
                "list_characters": self._list_characters,
                # Object handlers
                "create_object": self._create_object,
                "update_object": self._update_object,
                "delete_object": self._delete_object,
                "get_object": self._get_object,
                "list_objects": self._list_objects,
                # Parameter handlers
                "set_parameter": self._set_parameter,
                "delete_parameter": self._delete_parameter,
                "get_parameter": self._get_parameter,
                "list_parameters": self._list_parameters,
                "create_lorebook_entry": self._create_lorebook_entry,
            }
            
            handler = handlers.get(function_name)
            if handler:
                result = handler(arguments)
                logger.info(f"Executed {function_name}: {result.get('message', result)}")
                return result
            else:
                error = {"success": False, "error": f"Unknown function: {function_name}"}
                self.events.append(SSEEvent(EventType.ERROR, error))
                return error
                
        except Exception as e:
            logger.error(f"Error executing {function_name}: {e}", exc_info=True)
            error = {"success": False, "error": str(e)}
            self.events.append(SSEEvent(EventType.ERROR, error))
            return error
    
    def _create_node(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new node, or update if it already exists (upsert behavior)."""
        node_id = args.get('id')
        if not node_id:
            return {"success": False, "error": "Node id is required"}
        
        # If node exists, update it instead of failing
        if node_id in self.state.nodes:
            return self._update_node(args)
        
        node_data = {
            'id': node_id,
            'name': args.get('name', node_id),
            'definition': args.get('definition', ''),
            'explicit_state': args.get('explicit_state', args.get('description', '')),
            'implicit_state': args.get('implicit_state', ''),
            'properties': args.get('properties', {'status': []}),
            'actions': args.get('actions', []),
            'objects': args.get('objects', []),
            'triggers': args.get('triggers', []),
            'is_ending': args.get('is_ending', False)
        }
        
        # Normalize actions to ensure proper structure
        node_data['actions'] = self._normalize_actions(node_data['actions'])
        
        self.state.nodes[node_id] = node_data
        self.state.add_change('create', node_id)
        
        # The editor graph is derived from story.connections, not goto_node actions.
        new_edges = []
        
        # Emit node created event
        self.events.append(SSEEvent(
            event_type=EventType.NODE_CREATED,
            data={
                "node": node_data,
                "edges": new_edges,
                "position": self._calculate_position(len(self.state.nodes))
            }
        ))
        
        return {
            "success": True,
            "node_id": node_id,
            "message": f"Created node '{node_id}' with {len(node_data['actions'])} actions"
        }
    
    def _update_node(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing node."""
        node_id = args.get('id')
        if not node_id:
            return {"success": False, "error": "Node id is required"}
        
        if node_id not in self.state.nodes:
            return {"success": False, "error": f"Node '{node_id}' not found"}
        
        existing = self.state.nodes[node_id]
        updated_fields = []
        
        entity_fields = ['name', 'definition', 'explicit_state', 'implicit_state', 'properties', 
                         'actions', 'objects', 'triggers', 'is_ending']
        for field in entity_fields:
            if field in args and args[field] is not None:
                if field == 'actions':
                    existing[field] = self._normalize_actions(args[field])
                else:
                    existing[field] = args[field]
                updated_fields.append(field)
        
        if 'description' in args and args['description'] is not None and 'explicit_state' not in args:
            existing['explicit_state'] = args['description']
            updated_fields.append('explicit_state')
        
        self.state.add_change('update', node_id, fields=updated_fields)
        
        self.events.append(SSEEvent(
            event_type=EventType.NODE_UPDATED,
            data={
                "node": existing,
                "updated_fields": updated_fields
            }
        ))
        
        return {
            "success": True,
            "node_id": node_id,
            "message": f"Updated node '{node_id}' ({', '.join(updated_fields)})"
        }
    
    def _add_action_to_node(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Add a single action to a node without replacing existing ones."""
        node_id = args.get('node_id')
        action = args.get('action')
        
        if not node_id:
            return {"success": False, "error": "node_id is required"}
        if not action:
            return {"success": False, "error": "action is required"}
        
        if node_id not in self.state.nodes:
            return {"success": False, "error": f"Node '{node_id}' not found"}
        
        node = self.state.nodes[node_id]
        if 'actions' not in node:
            node['actions'] = []
        
        # Normalize the action
        normalized_action = self._normalize_actions([action])[0]
        action_id = normalized_action.get('id')
        
        # Check for duplicate
        existing_ids = {a.get('id') for a in node['actions']}
        if action_id in existing_ids:
            return {"success": False, "error": f"Action '{action_id}' already exists in node '{node_id}'"}
        
        node['actions'].append(normalized_action)
        self.state.add_change('add_action', node_id, action_id=action_id)
        
        new_edges = []
        
        self.events.append(SSEEvent(
            event_type=EventType.NODE_UPDATED,
            data={
                "node": node,
                "updated_fields": ["actions"],
                "added_action": normalized_action,
                "new_edges": new_edges
            }
        ))
        
        return {
            "success": True,
            "message": f"Added action '{action_id}' to node '{node_id}'"
        }
    
    def _add_object_to_node(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Add an object to a node without replacing existing ones."""
        node_id = args.get('node_id')
        obj = args.get('object')
        
        if not node_id:
            return {"success": False, "error": "node_id is required"}
        if not obj:
            return {"success": False, "error": "object is required"}
        
        if node_id not in self.state.nodes:
            return {"success": False, "error": f"Node '{node_id}' not found"}
        
        node = self.state.nodes[node_id]
        if 'objects' not in node:
            node['objects'] = []
        
        obj_id = obj.get('id')
        
        # Check for duplicate
        existing_ids = {o.get('id') for o in node['objects']}
        if obj_id in existing_ids:
            return {"success": False, "error": f"Object '{obj_id}' already exists in node '{node_id}'"}
        
        node['objects'].append(obj)
        self.state.add_change('add_object', node_id, object_id=obj_id)
        
        self.events.append(SSEEvent(
            event_type=EventType.OBJECT_ADDED,
            data={
                "node_id": node_id,
                "object": obj,
                "new_edges": []
            }
        ))
        
        return {
            "success": True,
            "message": f"Added object '{obj_id}' to node '{node_id}'"
        }
    
    def _delete_node(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Delete a node and its connected edges."""
        node_id = args.get('id')
        if not node_id:
            return {"success": False, "error": "Node id is required"}
        
        if node_id not in self.state.nodes:
            return {"success": False, "error": f"Node '{node_id}' not found"}
        
        # Remove the node
        deleted_node = self.state.nodes.pop(node_id)
        
        # Remove connected edges
        removed_edges = [e for e in self.state.edges 
                         if e.get('source') == node_id or e.get('target') == node_id]
        self.state.edges = [e for e in self.state.edges 
                           if e.get('source') != node_id and e.get('target') != node_id]
        
        self.state.add_change('delete', node_id)
        
        # Emit edge deleted events
        for edge in removed_edges:
            self.events.append(SSEEvent(EventType.EDGE_DELETED, edge))
        
        self.events.append(SSEEvent(
            event_type=EventType.NODE_DELETED,
            data={
                "node_id": node_id,
                "removed_edges": len(removed_edges)
            }
        ))
        
        return {
            "success": True,
            "message": f"Deleted node '{node_id}' and {len(removed_edges)} connected edges"
        }
    
    def _get_node(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get the current data of a node."""
        node_id = args.get('id')
        if not node_id:
            return {"success": False, "error": "Node id is required", "node": None}
        
        if node_id not in self.state.nodes:
            return {"success": False, "error": f"Node '{node_id}' not found", "node": None}
        
        node = self.state.nodes[node_id]
        return {
            "success": True,
            "node": node,
            "actions_count": len(node.get('actions', [])),
            "objects_count": len(node.get('objects', []))
        }
    
    def _list_nodes(self, args: Dict[str, Any] = None) -> Dict[str, Any]:
        """List all nodes in the graph."""
        # args is unused but required for consistent handler signature
        node_list = [
            {
                "id": n.get('id'),
                "name": n.get('name', n.get('id')),
                "actions_count": len(n.get('actions', [])),
                "has_ending": n.get('is_ending', False)
            }
            for n in self.state.nodes.values()
        ]
        return {
            "success": True,
            "nodes": node_list,
            "count": len(node_list)
        }
    
    def _normalize_actions(self, actions: List[Dict]) -> List[Dict]:
        """Normalize action format to handle common LLM mistakes."""
        normalized = []
        for action in actions:
            norm = dict(action)
            
            # Convert 'name' or 'label' to 'text'
            if 'text' not in norm:
                if 'name' in norm:
                    norm['text'] = norm.pop('name')
                elif 'label' in norm:
                    norm['text'] = norm.pop('label')
                elif 'description' in norm and 'text' not in norm:
                    norm['text'] = norm['description']
            
            # Convert target_node_id to proper effects
            if 'target_node_id' in norm and 'effects' not in norm:
                norm['effects'] = [{
                    'type': 'goto_node',
                    'target': norm.pop('target_node_id')
                }]
            
            # Normalize effects
            if 'effects' in norm:
                norm['effects'] = self._normalize_effects(norm['effects'])
            
            normalized.append(norm)
        
        return normalized
    
    def _normalize_effects(self, effects: List[Dict]) -> List[Dict]:
        """Normalize effect format to handle common LLM mistakes."""
        normalized = []
        for effect in effects:
            norm = dict(effect)
            
            # Handle 'effect' instead of 'type'
            if 'effect' in norm and 'type' not in norm:
                norm['type'] = norm.pop('effect')
            
            # Handle 'target_node' instead of 'target' for goto_node (LLM common mistake)
            if norm.get('type') == 'goto_node':
                if 'target_node' in norm and 'target' not in norm:
                    norm['target'] = norm.pop('target_node')
            
            # Handle 'variable' instead of 'target' for set_variable
            if norm.get('type') == 'set_variable':
                if 'variable' in norm and 'target' not in norm:
                    norm['target'] = norm.pop('variable')
            
            normalized.append(norm)
        
        return normalized
    
    def _extract_edges_from_node(self, node: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Legacy helper retained for compatibility."""
        return []
    
    def _extract_edges_from_action(self, source_id: str, action: Dict, 
                                    obj_name: Optional[str] = None) -> List[Dict]:
        """Legacy helper retained for compatibility."""
        return []
    
    def _rebuild_edges_for_node(self, node_id: str):
        """Editor-visible edges now come only from story.connections."""
        return None
    
    def _calculate_position(self, node_count: int) -> Dict[str, int]:
        """Calculate position for a new node."""
        # Simple grid layout
        cols = 4
        row = (node_count - 1) // cols
        col = (node_count - 1) % cols
        return {
            "x": 100 + col * 350,
            "y": 100 + row * 250
        }
    
    def get_pending_events(self) -> List[SSEEvent]:
        """Get and clear pending SSE events."""
        events = self.events.copy()
        self.events.clear()
        return events
    
    def get_final_state(self) -> Dict[str, Any]:
        """Get the final state after all operations."""
        # Count changes by entity type
        def count_by_type(entity_type: str, change_types: List[str]) -> int:
            return sum(1 for c in self.state.changes 
                      if c.details.get('entity_type') == entity_type 
                      and c.change_type in change_types)
        
        return {
            "nodes": list(self.state.nodes.values()),
            "edges": self.state.edges,
            "characters": list(self.state.characters.values()),
            "objects": list(self.state.objects.values()),
            "parameters": self.state.parameters,
            "changes": [
                {
                    "type": c.change_type,
                    "entity_id": c.node_id,
                    **c.details
                }
                for c in self.state.changes
            ],
            "summary": {
                "nodes_created": count_by_type('node', ['create']),
                "nodes_updated": count_by_type('node', ['update', 'add_action', 'add_object']),
                "nodes_deleted": count_by_type('node', ['delete']),
                "characters_created": count_by_type('character', ['create']),
                "characters_updated": count_by_type('character', ['update', 'add_placement']),
                "characters_deleted": count_by_type('character', ['delete']),
                "objects_created": count_by_type('object', ['create']),
                "objects_updated": count_by_type('object', ['update', 'add_state']),
                "objects_deleted": count_by_type('object', ['delete']),
                "parameters_set": count_by_type('parameter', ['set']),
                "parameters_deleted": count_by_type('parameter', ['delete']),
            }
        }
    
    # =========================================================================
    # CHARACTER HANDLERS
    # =========================================================================

    def _create_character(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new character."""
        char_id = args.get('id')
        if not char_id:
            return {"success": False, "error": "Character id is required"}
        
        # If character exists, update it instead of failing
        if char_id in self.state.characters:
            return self._update_character(args)
        
        char_data = {
            'id': char_id,
            'name': args.get('name', char_id),
            'definition': args.get('definition', ''),
            'explicit_state': args.get('explicit_state', args.get('description', '')),
            'implicit_state': args.get('implicit_state', ''),
            'properties': args.get('properties', {}),
            'is_playable': args.get('is_playable', False),
            'parameters': args.get('parameters', {}),
            'stats': args.get('stats', {})
        }
        
        self.state.characters[char_id] = char_data
        self.state.add_change('create', char_id, entity_type='character')
        
        self.events.append(SSEEvent(
            event_type=EventType.CHARACTER_CREATED,
            data={"character": char_data}
        ))
        
        return {
            "success": True,
            "character_id": char_id,
            "message": f"Created character '{args.get('name', char_id)}'"
        }
    
    def _update_character(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing character."""
        char_id = args.get('id')
        if not char_id:
            return {"success": False, "error": "Character id is required"}
        
        if char_id not in self.state.characters:
            return {"success": False, "error": f"Character '{char_id}' not found"}
        
        existing = self.state.characters[char_id]
        updated_fields = []
        
        entity_fields = ['name', 'definition', 'explicit_state', 'implicit_state', 'properties',
                         'is_playable', 'parameters', 'stats']
        for field in entity_fields:
            if field in args and args[field] is not None:
                existing[field] = args[field]
                updated_fields.append(field)
        
        if 'description' in args and args['description'] is not None and 'explicit_state' not in args:
            existing['explicit_state'] = args['description']
            updated_fields.append('explicit_state')
        
        self.state.add_change('update', char_id, entity_type='character', fields=updated_fields)
        
        self.events.append(SSEEvent(
            event_type=EventType.CHARACTER_UPDATED,
            data={"character": existing, "updated_fields": updated_fields}
        ))
        
        return {
            "success": True,
            "character_id": char_id,
            "message": f"Updated character '{char_id}' ({', '.join(updated_fields)})"
        }
    
    def _delete_character(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Delete a character."""
        char_id = args.get('id')
        if not char_id:
            return {"success": False, "error": "Character id is required"}
        
        if char_id not in self.state.characters:
            return {"success": False, "error": f"Character '{char_id}' not found"}
        
        del self.state.characters[char_id]
        self.state.add_change('delete', char_id, entity_type='character')
        
        self.events.append(SSEEvent(
            event_type=EventType.CHARACTER_DELETED,
            data={"character_id": char_id}
        ))
        
        return {"success": True, "message": f"Deleted character '{char_id}'"}
    
    def _get_character(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get character data."""
        char_id = args.get('id')
        if not char_id:
            return {"success": False, "error": "Character id is required", "character": None}
        
        if char_id not in self.state.characters:
            return {"success": False, "error": f"Character '{char_id}' not found", "character": None}
        
        return {"success": True, "character": self.state.characters[char_id]}
    
    def _list_characters(self, args: Dict[str, Any] = None) -> Dict[str, Any]:
        """List all characters."""
        char_list = [
            {
                "id": c.get('id'),
                "name": c.get('name', c.get('id')),
                "is_playable": c.get('is_playable', False)
            }
            for c in self.state.characters.values()
        ]
        return {"success": True, "characters": char_list, "count": len(char_list)}
    
    # =========================================================================
    # OBJECT HANDLERS
    # =========================================================================
    
    def _create_object(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new global object."""
        obj_id = args.get('id')
        if not obj_id:
            return {"success": False, "error": "Object id is required"}
        
        # If object exists, update it instead of failing
        if obj_id in self.state.objects:
            return self._update_object(args)
        
        obj_data = {
            'id': obj_id,
            'name': args.get('name', obj_id),
            'definition': args.get('definition', ''),
            'explicit_state': args.get('explicit_state', args.get('description', '')),
            'implicit_state': args.get('implicit_state', ''),
            'properties': args.get('properties', {'status': []}),
        }
        
        self.state.objects[obj_id] = obj_data
        self.state.add_change('create', obj_id, entity_type='object')
        
        self.events.append(SSEEvent(
            event_type=EventType.GLOBAL_OBJECT_CREATED,
            data={"object": obj_data}
        ))
        
        return {
            "success": True,
            "object_id": obj_id,
            "message": f"Created object '{args.get('name', obj_id)}'"
        }
    
    def _update_object(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing object."""
        obj_id = args.get('id')
        if not obj_id:
            return {"success": False, "error": "Object id is required"}
        
        if obj_id not in self.state.objects:
            return {"success": False, "error": f"Object '{obj_id}' not found"}
        
        existing = self.state.objects[obj_id]
        updated_fields = []
        
        entity_fields = ['name', 'definition', 'explicit_state', 'implicit_state', 'properties']
        for field in entity_fields:
            if field in args and args[field] is not None:
                existing[field] = args[field]
                updated_fields.append(field)
        
        if 'description' in args and args['description'] is not None and 'explicit_state' not in args:
            existing['explicit_state'] = args['description']
            updated_fields.append('explicit_state')
        
        self.state.add_change('update', obj_id, entity_type='object', fields=updated_fields)
        
        self.events.append(SSEEvent(
            event_type=EventType.GLOBAL_OBJECT_UPDATED,
            data={"object": existing, "updated_fields": updated_fields}
        ))
        
        return {
            "success": True,
            "object_id": obj_id,
            "message": f"Updated object '{obj_id}' ({', '.join(updated_fields)})"
        }
    
    def _delete_object(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Delete an object."""
        obj_id = args.get('id')
        if not obj_id:
            return {"success": False, "error": "Object id is required"}
        
        if obj_id not in self.state.objects:
            return {"success": False, "error": f"Object '{obj_id}' not found"}
        
        del self.state.objects[obj_id]
        self.state.add_change('delete', obj_id, entity_type='object')
        
        self.events.append(SSEEvent(
            event_type=EventType.GLOBAL_OBJECT_DELETED,
            data={"object_id": obj_id}
        ))
        
        return {"success": True, "message": f"Deleted object '{obj_id}'"}
    
    def _get_object(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get object data."""
        obj_id = args.get('id')
        if not obj_id:
            return {"success": False, "error": "Object id is required", "object": None}
        
        if obj_id not in self.state.objects:
            return {"success": False, "error": f"Object '{obj_id}' not found", "object": None}
        
        return {"success": True, "object": self.state.objects[obj_id]}
    
    def _list_objects(self, args: Dict[str, Any] = None) -> Dict[str, Any]:
        """List all objects."""
        obj_list = [
            {
                "id": o.get('id'),
                "name": o.get('name', o.get('id')),
                "has_definition": bool(o.get('definition'))
            }
            for o in self.state.objects.values()
        ]
        return {"success": True, "objects": obj_list, "count": len(obj_list)}
    
    # =========================================================================
    # PARAMETER HANDLERS
    # =========================================================================
    
    def _set_parameter(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Set a parameter value."""
        key = args.get('key')
        value = args.get('value')
        
        if not key:
            return {"success": False, "error": "Parameter key is required"}
        
        is_new = key not in self.state.parameters
        self.state.parameters[key] = value
        self.state.add_change('set', key, entity_type='parameter', is_new=is_new)
        
        self.events.append(SSEEvent(
            event_type=EventType.PARAMETER_SET,
            data={"key": key, "value": value, "is_new": is_new}
        ))
        
        action = "Created" if is_new else "Updated"
        return {"success": True, "message": f"{action} parameter '{key}'"}
    
    def _delete_parameter(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Delete a parameter."""
        key = args.get('key')
        if not key:
            return {"success": False, "error": "Parameter key is required"}
        
        if key not in self.state.parameters:
            return {"success": False, "error": f"Parameter '{key}' not found"}
        
        del self.state.parameters[key]
        self.state.add_change('delete', key, entity_type='parameter')
        
        self.events.append(SSEEvent(
            event_type=EventType.PARAMETER_DELETED,
            data={"key": key}
        ))
        
        return {"success": True, "message": f"Deleted parameter '{key}'"}
    
    def _get_parameter(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get a parameter value."""
        key = args.get('key')
        if not key:
            return {"success": False, "error": "Parameter key is required", "value": None}
        
        if key not in self.state.parameters:
            return {"success": False, "error": f"Parameter '{key}' not found", "value": None}
        
        return {"success": True, "key": key, "value": self.state.parameters[key]}
    
    def _list_parameters(self, args: Dict[str, Any] = None) -> Dict[str, Any]:
        """List all parameters."""
        param_list = []
        for key, value in self.state.parameters.items():
            value_type = type(value).__name__
            preview = str(value)[:50] + "..." if len(str(value)) > 50 else str(value)
            param_list.append({
                "key": key,
                "type": value_type,
                "preview": preview
            })
        return {"success": True, "parameters": param_list, "count": len(param_list)}
    
    def _create_lorebook_entry(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Create a lorebook entry (prefixed with lore_)."""
        name = args.get('name')
        content = args.get('content')
        
        if not name:
            return {"success": False, "error": "Lorebook entry name is required"}
        if not content:
            return {"success": False, "error": "Lorebook content is required"}
        
        # Add lore_ prefix if not present
        key = name if name.startswith('lore_') else f'lore_{name}'
        
        is_new = key not in self.state.parameters
        self.state.parameters[key] = content
        self.state.add_change('set', key, entity_type='parameter', is_new=is_new, is_lorebook=True)
        
        self.events.append(SSEEvent(
            event_type=EventType.PARAMETER_SET,
            data={"key": key, "value": content, "is_new": is_new, "is_lorebook": True}
        ))
        
        action = "Created" if is_new else "Updated"
        return {"success": True, "message": f"{action} lorebook entry '{key}'"}
