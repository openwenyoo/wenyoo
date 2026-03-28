import lupa
import asyncio
import copy
from lupa import LuaRuntime
from src.models.game_state import GameState

import logging
logger = logging.getLogger(__name__)

# Lua globals that are safe for story scripts.
# Everything not on this list is removed from the sandbox.
_LUA_SAFE_GLOBALS = frozenset({
    "assert", "error", "ipairs", "next", "pairs", "pcall", "xpcall",
    "rawequal", "rawget", "rawlen", "rawset", "select",
    "tonumber", "tostring", "type", "unpack",
    "math", "string", "table", "coroutine",
})


class LuaRuntimeService:
    def __init__(self, game_kernel: 'GameKernel'):
        self.game_kernel = game_kernel
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self._strip_dangerous_globals()
        self.text_buffer = []
        self.async_text_buffer = []

    def _strip_dangerous_globals(self):
        """Remove dangerous Lua standard libraries from the runtime."""
        g = self.lua.globals()
        for name in ("io", "os", "package", "debug", "loadfile", "dofile", "require"):
            try:
                g[name] = None
            except Exception:
                pass

    def _get_player_inventory(self, player_id: str, game_state: GameState):
        return game_state.get_player_inventory(player_id)

    def _add_to_inventory(self, player_id: str, item_id: str, game_state: GameState):
        item_to_add = self.game_kernel.story_manifest.get_object(item_id)
        if item_to_add:
            inventory = self._get_player_inventory(player_id, game_state)
            if item_id not in inventory:
                inventory.append(item_id)

    def _remove_from_inventory(self, player_id: str, item_id: str, game_state: GameState):
        inventory = self._get_player_inventory(player_id, game_state)
        for i, current_item_id in enumerate(inventory):
            if current_item_id == item_id:
                inventory.pop(i)
                break

    def _set_variable(self, key: str, value: any, game_state: GameState):
        
        def to_python(lua_obj):
            # Use lupa.lua_type to correctly check if the object is a table
            if lupa.lua_type(lua_obj) == 'table':
                py_dict = {}
                for k, v in lua_obj.items():
                    py_dict[k] = to_python(v)
                return py_dict
            return lua_obj

        python_value = to_python(value)
        game_state.set_variable(key, python_value)

    def _get_variable(self, key: str, default: any, game_state: GameState):
        value = game_state.get_variable(key, default)
        if isinstance(value, dict):
            serializable_value = copy.deepcopy(value)
            for p_id, p_data in serializable_value.items():
                if isinstance(p_data, dict) and 'inventory' in p_data:
                    p_data['inventory'] = list(p_data['inventory'])
            return self.lua.table_from(serializable_value)
        
        if isinstance(value, list):
            return self.lua.table_from(value)
            
        return value

    def _update_object_status(self, object_id: str, add_status: list, remove_status: list, game_state: GameState):
        """Update an object's status tags from Lua scripts."""
        game_state.update_object_status(object_id, add_status=add_status, remove_status=remove_status)

    def _display_text(self, player_id, message):
        asyncio.create_task(self.game_kernel.frontend_adapter.send_game_message(message, player_id))

    def _display_text_buffered(self, player_id, message):
        self.async_text_buffer.append((player_id, message))

    def get_text_buffer(self) -> list[str]:
        """Returns the current text buffer."""
        return self.text_buffer

    def clear_text_buffer(self):
        """Clears the text buffer."""
        self.text_buffer = []

    def create_sandboxed_environment(self, player_id: str, game_state: GameState, use_async_display: bool = False):
        lua_globals = self.lua.globals()
        
        def lua_print(*args):
            self.text_buffer.append(" ".join(map(str, args)))

        display_func = self._display_text_buffered if use_async_display else self._display_text
        game_functions = {
            'get_player_inventory': lambda _,: self._get_player_inventory(player_id, game_state),
            'add_to_inventory': lambda _, item_id: self._add_to_inventory(player_id, item_id, game_state),
            'remove_from_inventory': lambda _, item_id: self._remove_from_inventory(player_id, item_id, game_state),
            'set_variable': lambda _, key, value: self._set_variable(key, value, game_state),
            'get_variable': lambda _, key, default=None: self._get_variable(key, default, game_state),
            'update_object_status': lambda _, object_id, add_status, remove_status: self._update_object_status(object_id, add_status or [], remove_status or [], game_state),
            'display_text': lambda _, message: display_func(player_id, message),
            'print': lua_print,
        }

        lua_game_table = self.lua.table_from(game_functions)

        if hasattr(game_state, 'function_parameters') and player_id in game_state.function_parameters:
            lua_game_table.parameters = self.lua.table_from(game_state.function_parameters[player_id])

        lua_globals.game = lua_game_table
        lua_globals.player_id = player_id

        return lua_globals

    def execute_script(self, script: str, player_id: str, game_state: GameState):
        env = self.create_sandboxed_environment(player_id, game_state, use_async_display=False)
        self.lua.execute(script, env)

    async def execute_script_async(self, script: str, player_id: str, game_state: GameState):
        self.async_text_buffer = []
        env = self.create_sandboxed_environment(player_id, game_state, use_async_display=True)
        self.lua.execute(script, env)

        for p_id, msg in self.async_text_buffer:
            await self.game_kernel.frontend_adapter.send_game_message(msg, p_id)
        
        self.async_text_buffer = []

    def execute_script_with_return(self, script: str, player_id: str, game_state: GameState) -> any:
        env = self.create_sandboxed_environment(player_id, game_state)
        result = self.lua.execute(script, env)

        def to_python(lua_obj):
            if lupa.lua_type(lua_obj) == 'table':
                py_dict = {}
                for k, v in lua_obj.items():
                    py_dict[k] = to_python(v)
                return py_dict
            return lua_obj

        return to_python(result)

    def execute_function(self, function_name: str, *args):
        lua_func = self.lua.globals()[function_name]
        return lua_func(*args)

    def evaluate_expression(self, expression: str, game_state: GameState, player_id: str = "default") -> any:
        """
        Evaluate a Lua expression and return the result.
        
        This is used for derived variables - variables whose values are computed
        from other variables using Lua expressions.
        
        Args:
            expression: A Lua expression string (e.g., "base_attack + weapon_bonus")
            game_state: The current game state
            player_id: The player ID for context
            
        Returns:
            The evaluated result (number, string, bool, or dict/list)
        """
        # Create a sandboxed environment with read-only access to variables
        lua_globals = self.lua.globals()
        
        # Expose variables directly as Lua globals for easy access
        # e.g., "base_attack + strength" instead of "game:get_variable('base_attack')"
        for key, value in game_state.variables.items():
            if key == 'players':
                # Skip players to avoid circular reference issues
                continue
            if isinstance(value, str) and value.startswith('$lua:'):
                # Skip other derived variables to prevent infinite recursion
                continue
            if isinstance(value, dict):
                try:
                    lua_globals[key] = self.lua.table_from(value)
                except Exception:
                    lua_globals[key] = value
            elif isinstance(value, list):
                try:
                    lua_globals[key] = self.lua.table_from(value)
                except Exception:
                    lua_globals[key] = value
            else:
                lua_globals[key] = value
        
        # Expose player character data via pointer model
        if player_id:
            lua_globals['player_id'] = player_id
            char_id = game_state.get_controlled_character_id(player_id)
            if char_id and char_id in game_state.character_states:
                char_state = game_state.character_states[char_id]
                char_dict = {k: v for k, v in char_state.items() if isinstance(v, (str, int, float, bool, list, dict))}
                lua_globals['player_character'] = self.lua.table_from(char_dict)
                stats = char_state.get('properties', {}).get('stats', {})
                if stats:
                    lua_globals['player_stats'] = self.lua.table_from(stats)
        
        # Expose math library for convenience
        self.lua.execute("math = math or {}")
        
        # Wrap expression in a return statement for evaluation
        wrapped_script = f"return ({expression})"
        
        try:
            result = self.lua.execute(wrapped_script)
            
            # Convert Lua table back to Python dict/list
            if lupa.lua_type(result) == 'table':
                return self._lua_table_to_python(result)
            
            return result
        except Exception as e:
            logger.warning(f"Failed to evaluate Lua expression '{expression}': {e}")
            return None

    def _lua_table_to_python(self, lua_obj) -> any:
        """Convert a Lua table to Python dict or list."""
        if lupa.lua_type(lua_obj) != 'table':
            return lua_obj
        
        # Check if it's an array-like table (sequential integer keys starting at 1)
        is_array = True
        max_index = 0
        for k, v in lua_obj.items():
            if not isinstance(k, int) or k < 1:
                is_array = False
                break
            max_index = max(max_index, k)
        
        if is_array and max_index > 0:
            # Convert to list
            result = [None] * max_index
            for k, v in lua_obj.items():
                result[k - 1] = self._lua_table_to_python(v)
            return result
        else:
            # Convert to dict
            result = {}
            for k, v in lua_obj.items():
                result[k] = self._lua_table_to_python(v)
            return result
