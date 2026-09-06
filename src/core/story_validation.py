"""Author-facing diagnostics for resolved YAML data. No LLM calls or mutations."""
from collections import Counter
import copy

from pydantic import ValidationError

from src.models.story_models import (
    Character, Connection, FormDefinition, Function, StoryAction, StoryNode, StoryObject, Trigger,
)


def validate_story_data(data):
    issues = []

    def report(code, message, path, entity=None, kind="story", severity="error", hint=""):
        issues.append(dict(code=code, severity=severity, message=message, path=path,
                           entity_id=entity, entity_type=kind, hint=hint))

    if not isinstance(data, dict):
        report("structure", "Story must be a mapping.", [])
        return issues

    nodes = data.get("nodes") or {}
    if not isinstance(nodes, dict):
        report("structure", "Nodes must be a mapping keyed by node ID.", ["nodes"])
        return issues
    entities = {key: {} for key in ("node", "character", "object", "form", "function")}
    all_ids = {}

    def register(kind, key, value, path, model):
        if not isinstance(value, dict):
            report("structure", f"{kind.title()} must be a mapping.", path, key, kind)
            return
        if not isinstance(key, str) or not key.strip():
            report("missing_id", f"{kind.title()} needs an ID.", path, key, kind)
            return
        if kind in ("node", "character", "object") and key in all_ids:
            report("duplicate_id", f"ID '{key}' is already used by {all_ids[key]}.", path, key, kind,
                   hint="Give every entity, including each physical item, its own ID.")
        all_ids[key] = kind
        entities[kind][key] = value
        if value.get("id") and value["id"] != key:
            report("id_mismatch", f"ID '{value['id']}' disagrees with key '{key}'.", path + ["id"], key, kind)
        try:
            model.model_validate(copy.deepcopy({**value, "id": key}))
        except ValidationError as exc:
            for error in exc.errors():
                report("schema", error["msg"], path + list(error["loc"]), key, kind)
        if kind in ("node", "character", "object") and not str(value.get("definition") or "").strip():
            report("missing_definition", f"'{key}' has no authored definition or rules.", path + ["definition"],
                   key, kind, "warning", "Describe the entity and how it should behave.")

    def register_list(kind, values, path, model):
        if not isinstance(values, list):
            report("structure", f"{kind.title()} collection must be a list.", path)
            return
        for i, value in enumerate(values):
            register(kind, value.get("id") if isinstance(value, dict) else None, value, path + [i], model)

    for key, value in nodes.items():
        register("node", key, value, ["nodes", key], StoryNode)
    register_list("character", data.get("characters") or [], ["characters"], Character)
    register_list("object", data.get("objects") or [], ["objects"], StoryObject)
    for key, value in nodes.items():
        if isinstance(value, dict):
            register_list("object", value.get("objects") or [], ["nodes", key, "objects"], StoryObject)
    for field, kind, model in (("forms", "form", FormDefinition), ("functions", "function", Function)):
        values = data.get(field) or {}
        if field == "functions" and isinstance(values, list):
            register_list(kind, values, [field], model)
        elif isinstance(values, dict):
            for key, value in values.items():
                register(kind, key, value, [field, key], model)
        else:
            report("structure", f"{field.title()} must be a mapping.", [field])

    def reference(kind, target, path, entity=None, owner_kind="node"):
        # Template/Lua targets resolve at runtime. Static checks cannot prove them broken.
        if isinstance(target, str) and target and not any(c in target for c in "{}$"):
            if target not in entities[kind]:
                report("broken_reference", f"Unknown {kind} '{target}'.", path, entity, owner_kind,
                       hint="Select an existing ID or define the missing entity.")

    start = data.get("start_node_id", data.get("start_node", "start"))
    if not isinstance(start, str):
        report("structure", "Starting node must be an ID string.", ["start_node_id"])
    reference("node", start, ["start_node_id"], start)
    if not nodes or not start:
        report("missing_start", "Choose a starting node.", ["start_node_id"])
    adjacency = {key: set() for key in nodes}
    owners = {}
    for key, character in entities["character"].items():
        props = character.get("properties") or {}
        if not isinstance(props, dict):
            continue
        reference("node", props.get("location"), ["characters", key, "properties", "location"], key, "character")
        inventory = props.get("inventory") or []
        if not isinstance(inventory, list):
            report("inventory_type", "Inventory must be a list of object IDs.", ["characters", key], key, "character")
            continue
        for item in inventory:
            item_id = item.get("id") if isinstance(item, dict) else item
            path = ["characters", key, "properties", "inventory"]
            if not isinstance(item_id, str):
                report("inventory_type", "Each inventory entry needs an object ID.", path, key, "character")
                continue
            reference("object", item_id, path, key, "character")
            if item_id in owners:
                report("inventory_ownership", f"'{item_id}' is in both '{owners[item_id]}' and '{key}' inventories.",
                       path, key, "character", hint="Separate physical items need separate IDs. Transfer one item between owners.")
            owners[item_id] = key

    def walk(value, path, node_id=None):
        if isinstance(value, list):
            ids = [v.get("id") for v in value if isinstance(v, dict) and isinstance(v.get("id"), str)]
            for key, count in Counter(ids).items():
                if count > 1:
                    report("duplicate_id", f"ID '{key}' occurs {count} times in this list.", path, node_id)
            for i, item in enumerate(value):
                walk(item, path + [i], node_id)
        elif isinstance(value, dict):
            equals = {}
            for condition in value.get("conditions", []) if isinstance(value.get("conditions"), list) else []:
                if not isinstance(condition, dict):
                    continue
                variable = condition.get("variable")
                if (isinstance(variable, str) and condition.get("type") == "variable"
                        and condition.get("operator", "eq") in ("eq", "==")):
                    if variable in equals and equals[variable] != condition.get("value"):
                        report("contradictory_conditions", f"'{variable}' must equal different values at the same time.",
                               path + ["conditions"], node_id, severity="warning",
                               hint="Check whether these conditions should be alternatives instead of all required.")
                    equals[variable] = condition.get("value")
            effect_type = value.get("type", value.get("effect"))
            target = value.get("target")
            if effect_type == "goto_node":
                reference("node", target, path + ["target"], node_id)
                if node_id in adjacency and isinstance(target, str) and target in nodes:
                    adjacency[node_id].add(target)
            elif effect_type == "present_form":
                reference("form", value.get("form_id"), path + ["form_id"], node_id)
            elif effect_type == "set_controlled_character":
                reference("character", target, path + ["target"], node_id)
            elif effect_type == "call_function":
                reference("function", value.get("function"), path + ["function"], node_id)
            elif effect_type in ("add_to_inventory", "remove_from_inventory", "set_object_state", "update_object_status"):
                reference("object", target, path + ["target"], node_id)
            for key, nested in value.items():
                walk(nested, path + [key], node_id)

    for key, value in nodes.items():
        walk(value, ["nodes", key], key)
    for field in ("actions", "triggers", "forms", "functions"):
        walk(data.get(field), [field])
    for field, model in (("actions", StoryAction), ("triggers", Trigger)):
        values = data.get(field) or []
        if not isinstance(values, list):
            report("structure", f"{field.title()} must be a list.", [field])
            continue
        for i, value in enumerate(values):
            try:
                model.model_validate(copy.deepcopy(value))
            except ValidationError as exc:
                report("schema", str(exc), [field, i])
    if not isinstance(data.get("initial_variables", {}), dict):
        report("structure", "Initial variables must be a mapping.", ["initial_variables"])

    connections = data.get("connections") or []
    if isinstance(connections, dict):
        connections = connections.get("connections", [])
    if not isinstance(connections, list):
        report("structure", "Connections must be a list.", ["connections"])
        connections = []
    world_ids = set().union(*(set(entities[k]) for k in ("node", "character", "object")))
    for i, connection in enumerate(connections):
        try:
            conn = Connection.model_validate(connection)
        except ValidationError as exc:
            report("schema", str(exc), ["connections", i])
            continue
        for target in [conn.source, *conn.targets]:
            if target not in world_ids:
                report("broken_connection", f"Connection refers to unknown entity '{target}'.", ["connections", i], conn.id, "connection")
        if conn.source in adjacency:
            adjacency[conn.source].update(t for t in conn.targets if t in nodes)
    seen, queue = set(), [start]
    while queue:
        key = queue.pop()
        if isinstance(key, str) and key not in seen:
            seen.add(key)
            queue.extend(adjacency.get(key, set()) - seen)
    for key in nodes.keys() - seen:
        report("unreachable", f"No static path from the start to '{key}'.", ["nodes", key], key, severity="warning",
               hint="Add a path, or confirm this node is reached through authored intent, Lua, or dynamic generation.")
    return issues
