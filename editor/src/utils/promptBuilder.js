/**
 * Prompt Builder - Constructs comprehensive prompts for the LLM
 * Includes node format specification, story context, and user request
 */

import { generateOutline } from './storyAnalyzer.js';
import { EDITOR_PROMPT_LANGUAGE_SECTION } from './editorPromptLanguage.js';

// We'll load the node format description at runtime
let nodeFormatDoc = '';

/**
 * Initialize the prompt builder by loading the node format description
 * This should be called once when the app starts
 */
export async function initPromptBuilder() {
    try {
        // Load the node format description from the prompts directory
        const response = await fetch('/prompts/node_format_description.md');
        if (response.ok) {
            nodeFormatDoc = await response.text();
        } else {
            console.warn('Could not load node_format_description.md');
            nodeFormatDoc = 'Node format description not available';
        }
    } catch (error) {
        console.error('Error loading node format description:', error);
        nodeFormatDoc = 'Node format description not available';
    }
}

/**
 * Build a comprehensive prompt for the LLM
 * @param {string} userRequest - The user's request/instruction
 * @param {Array} selectedNodes - Currently selected nodes
 * @param {Object} storyData - The complete story data
 * @param {Array} allNodes - All nodes in the graph
 * @param {Array} edges - All edges in the graph
 * @returns {string} The complete prompt
 */
export function buildPrompt(userRequest, selectedNodes, storyData, allNodes, edges) {
    const analysis = storyData.metadata?.analysis || {};
    const metadata = storyData.metadata || {};

    const outline = generateBriefOutline(allNodes);
    const selectionContext = buildSelectionContext(selectedNodes, allNodes, edges);

    return `# ROLE
You are an expert story editor for an AI native text based game engine. Your task is to help create and modify story nodes while maintaining consistency with the existing story's style and structure.

# NODE FORMAT SPECIFICATION
${nodeFormatDoc || 'Please follow the standard YAML format for this AI native text based game engine.'}

# CURRENT STORY CONTEXT
Title: ${metadata.title || 'Untitled Story'}
Genre: ${metadata.genre || 'Unknown'}

## Story Analysis
Vibe: ${analysis.vibe || 'Not analyzed yet'}
Tone: ${analysis.tone || 'Not analyzed yet'}
Vocabulary Level: ${analysis.vocabulary_level || 'Not analyzed yet'}
Narrative Perspective: ${analysis.perspective || 'Not analyzed yet'}
Themes: ${analysis.themes?.join(', ') || 'Not analyzed yet'}

## Story Outline (Brief)
${outline}

${selectionContext ? `# SELECTED NODES CONTEXT
${formatSelectionContext(selectionContext)}
` : ''}
# USER REQUEST
${userRequest}

# LANGUAGE
${EDITOR_PROMPT_LANGUAGE_SECTION.replace('# LANGUAGE\n', '')}

# CRITICAL INSTRUCTIONS
1. **Maintain Consistency**: Match the story's vibe, tone, vocabulary level, and perspective
2. **Follow Format Exactly**: Use the node format specification above - this is CRITICAL
3. **Required Fields**: Every node MUST have: id, name, explicit_state (DSPP model)
4. **Actions Format**: Actions MUST have: id, text (LLM uses for intent matching), and may use \`intent\` instead of only structured \`effects\`
5. **Navigation**: Use \`target\` in goto_node effects
6. **Proper Indentation**: Use 2 spaces for YAML indentation
7. **Preserve Connections**: Maintain existing edges to/from nodes unless explicitly asked to change

# OUTPUT FORMAT
You can respond with either a SINGLE operation or MULTIPLE operations:

## Single Operation Format:
{
  "operation": "create_nodes" | "update_nodes" | "replace_nodes",
  "nodes": [ /* node objects */ ],
  "edges": [ /* edge objects */ ],
  "explanation": "Brief explanation"
}

## Multi-Operation Format (for complex changes):
{
  "operations": [
    {
      "operation": "create_nodes",
      "nodes": [ /* new nodes */ ],
      "edges": [ /* edges between new nodes */ ],
      "explanation": "Created new content"
    },
    {
      "operation": "update_nodes",
      "nodes": [ /* modified existing nodes */ ],
      "edges": [],
      "explanation": "Linked existing node to new content"
    }
  ]
}

## Operation Types:

### create_nodes
Use when: Adding new nodes to the story
- Include ONLY the new nodes in the "nodes" array
- Include edges between the new nodes
- DO NOT include existing nodes

### update_nodes
Use when: Modifying existing nodes
- Include ONLY the nodes being modified (with their complete data)
- When adding actions: Include ALL existing actions PLUS the new ones
- Common use: Adding a new action with goto_node effect to link to new content
- The system will auto-create edges from goto_node effects

### replace_nodes
Use when: Completely replacing selected nodes with new content
- Remove selected nodes and add new ones in their place

## LINKING NEW CONTENT TO EXISTING NODES

When creating new nodes that should be accessible from existing nodes, use BOTH operations:

Example - "Add a secret room accessible from the library":

{
  "operations": [
    {
      "operation": "create_nodes",
      "nodes": [
        {
          "id": "secret_room",
          "name": "Secret Room",
          "explicit_state": "A hidden chamber behind the bookshelf...",
          "definition": "",
          "implicit_state": "",
          "properties": {},
          "objects": [],
          "actions": [
            {
              "id": "return_to_library",
              "text": "Return to the library",
              "effects": [
                { "type": "goto_node", "target": "library" }
              ]
            }
          ],
          "triggers": []
        }
      ],
      "edges": [],
      "explanation": "Created secret room node"
    },
    {
      "operation": "update_nodes",
      "nodes": [
        {
          "id": "library",
          "actions": [
            /* Include ALL existing actions from the library node */
            {
              "id": "examine_books",
              "text": "Examine the books",
              "effects": [
                { "type": "display_text", "text": "Ancient tomes line the shelves..." }
              ]
            },
            /* THEN add the new linking action */
            {
              "id": "enter_secret_room",
              "text": "Push the hidden bookshelf",
              "effects": [
                { "type": "display_text", "text": "The bookshelf swings open, revealing a passage!" },
                { "type": "goto_node", "target": "secret_room" }
              ]
            }
          ]
        }
      ],
      "edges": [],
      "explanation": "Added secret passage action to library"
    }
  ]
}

IMPORTANT: 
- When updating nodes, include the COMPLETE actions array (all existing + new)
- The system will automatically create edges from goto_node effects
- Use multi-operation format when you need to both create and link content`;
}

/**
 * Build context about selected nodes
 * @param {Array} selectedNodes - Selected nodes from React Flow
 * @param {Array} allNodes - All nodes
 * @param {Array} edges - All edges
 * @returns {Object|null} Selection context or null if no selection
 */
function buildSelectionContext(selectedNodes, allNodes, edges) {
    if (!selectedNodes || selectedNodes.length === 0) {
        return null;
    }

    const selectedIds = selectedNodes.map(n => n.id);

    return {
        nodes: selectedNodes.map(n => n.data),
        incoming: edges.filter(e => selectedIds.includes(e.target)),
        outgoing: edges.filter(e => selectedIds.includes(e.source)),
        count: selectedNodes.length
    };
}

/**
 * Generate a brief outline of the story
 * @param {Array} nodes - All nodes
 * @returns {string} Brief outline
 */
function generateBriefOutline(nodes) {
    if (!nodes || nodes.length === 0) {
        return 'No nodes in story yet';
    }

    const maxNodesToShow = 10;
    const nodesToShow = nodes.slice(0, maxNodesToShow);

    const outline = nodesToShow.map(n => {
        const data = n.data || n;
        const desc = data.description || 'No description';
        const summary = desc.length > 60 ? desc.substring(0, 60) + '...' : desc;
        return `- ${data.id}: ${summary}`;
    }).join('\n');

    const remaining = nodes.length - maxNodesToShow;
    return outline + (remaining > 0 ? `\n... and ${remaining} more nodes` : '');
}

/**
 * Format selection context for the prompt
 * @param {Object} context - Selection context
 * @returns {string} Formatted context
 */
function formatSelectionContext(context) {
    const nodeList = context.nodes.map(n => n.id).join(', ');

    let result = `Selected ${context.count} node(s): ${nodeList}\n\n`;

    if (context.incoming.length > 0) {
        result += `Incoming connections:\n`;
        result += context.incoming.map(e => `  - ${e.source} → ${e.target}${e.label ? ` (${e.label})` : ''}`).join('\n');
        result += '\n\n';
    }

    if (context.outgoing.length > 0) {
        result += `Outgoing connections:\n`;
        result += context.outgoing.map(e => `  - ${e.source} → ${e.target}${e.label ? ` (${e.label})` : ''}`).join('\n');
        result += '\n\n';
    }

    result += `Full node data:\n`;
    result += JSON.stringify(context.nodes, null, 2);

    return result;
}
