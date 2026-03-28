# Prompt Templates

This directory contains all LLM prompt templates used by Wenyoo.
All prompts follow a unified format for consistency and maintainability.

## Generation Prompts

These prompts are used for dynamic content generation during gameplay.

| File | Purpose | Used By |
|------|---------|---------|
| `generate_node.txt` | Generate complete story nodes with objects, characters, actions | `NodeGenerator` |
| `generate_object.txt` | Generate individual objects | `Architect` (entity generation) |
| `generate_character.txt` | Generate individual characters | `Architect` (entity generation) |

### Common Format

All generation prompts use this structure:
```
=== OUTPUT FORMAT ===
(Expected output structure with examples)

=== RULES ===
(Constraints and guidelines)

=== CONTEXT/DESCRIPTION ===
{placeholder_variables}

=== HINTS ===
{hints}
```

### Placeholder Variables

| Variable | Description |
|----------|-------------|
| `{story_context}` | Story title, genre, setting |
| `{generation_prompt}` | Specific generation instructions |
| `{available_locations}` | Valid node IDs for connections |
| `{hints}` | Optional guidance for generation |
| `{brief}` | Brief description (for object/character) |

## Interaction Prompts

These prompts handle player input and NPC interactions.

| File | Purpose |
|------|---------|
| `dialogue_prompt.txt` | Generate NPC dialogue responses |
| `intent_parser_prompt.txt` | Parse player intent from natural language |
| `action_parser_prompt.txt` | Match player input to available actions |
| `help_prompt.txt` | Generate contextual help |
| `system_prompt.txt` | Base system context for LLM |

## Documentation

| File | Purpose |
|------|---------|
| `node_format_description.md` | Complete node YAML format reference |
| `story_format_description.md` | Complete story YAML format reference |

## Entity Model

All generated content uses the DSPP entity model (Definition, State, Perception, Properties):

### For Objects
```yaml
id: object_id
name: "Object Name"
definition: |        # Static: interaction rules, description
  [Description]
  Physical description...
  
  [Interaction Rules]
  ## Examine
  When player examines: ...
explicit_state: "..."      # Dynamic: current visible state
implicit_state: "..."    # Dynamic: hidden state (optional)
properties:
  status: []          # Dynamic: status tags
```

### For Characters
```yaml
id: character_id
name: "Character Name"
definition: |         # Static: identity, personality, behavior
  ## Identity
  Who they are...
  
  ## Personality
  How they behave...
  
  ## Behavior Rules
  ### Greeting
  When player greets: ...
explicit_state: "..."      # Dynamic: current appearance
implicit_state: "..."    # Dynamic: hidden thoughts (optional)
memory: []            # Dynamic: accumulated experiences
properties:
  status: []
  inventory: []
  affinity: 50
```

### For Nodes
```yaml
id: node_id
name: "Node Name"
definition: |         # Static: generation template (optional)
  Location type, atmosphere, what should be here...
explicit_state: |          # Dynamic: current visible description
  Rich description with {object_id: links} and {@char_id: characters}...
implicit_state: "..."    # Dynamic: hidden secrets (optional)
```

## Effect Format in Definitions

When definitions include behavior rules with effects, use JSON format:
```
## Take
When player takes this:
- Generate effect: {"type": "add_to_inventory", "value": "object_id"}
- Generate effect: {"type": "set_variable", "target": "has_item", "value": true}
```

## Language Handling

All prompts include instructions to match the language of the input content:
```
All text content MUST be in the same language as the description provided below.
```

This ensures generated content matches the story's language (Chinese, English, etc.).

## Adding New Prompts

1. Create the prompt file in this directory
2. Use the standard section format (`=== SECTION ===`)
3. Include `{placeholder}` variables for dynamic content
4. Document in this README
5. Update the code to load and use the prompt file
