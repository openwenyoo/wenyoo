import axios from 'axios';
import { editorFetch } from './editorApi.js';
import { buildPrompt } from '../utils/promptBuilder.js';
import { parseAIResponse } from '../utils/aiResponseParser.js';
import { applyAIChanges } from '../utils/graphOperations.js';
import { appendEditorLanguageSection } from '../utils/editorPromptLanguage.js';

/**
 * Generate change summary for multi-operation responses
 */
export const generateChangeSummary = (operations) => {
    const stats = {
        created: 0,
        updated: 0,
        replaced: 0,
        edgesAdded: 0
    };

    operations.forEach(op => {
        if (op.operation === 'create_nodes') stats.created += op.nodes.length;
        if (op.operation === 'update_nodes') stats.updated += op.nodes.length;
        if (op.operation === 'replace_nodes') stats.replaced += op.nodes.length;
        stats.edgesAdded += op.edges.length;
    });

    return `📝 Nodes created: ${stats.created}
✏️ Nodes updated: ${stats.updated}
🔄 Nodes replaced: ${stats.replaced}
🔗 Connections added: ${stats.edgesAdded}`;
};

export const buildBatchConvertPrompt = ({
    pseudoContext,
    edgeContext,
    realNodeContext,
}) => appendEditorLanguageSection(`
You are an AI assistant for the Wenyoo editor. Wenyoo is an AI native text based game engine.
Your task is to convert "Pseudo-Nodes" (placeholders with prompts) into full "Detailed Nodes" and update connections.

CONTEXT:
--- PSEUDO NODES TO CONVERT ---
${pseudoContext}

--- EXISTING CONNECTIONS ---
${edgeContext}

--- CONNECTED REAL NODES (For Context) ---
${realNodeContext}

INSTRUCTIONS:
1. For each Pseudo-Node, generate a full node definition (id, name, definition, explicit_state, implicit_state, properties, objects, actions, triggers).
   - Use the ID of the pseudo-node for the new real node (or a derived one, but keeping it simple is better).
   - The content should be based on the user's prompt.
2. You may also need to update EXISTING nodes.
   - For example, if an existing node connects TO a pseudo-node, you might want to add an Action to the existing node that leads to the new node.
   - If a pseudo-node connects TO an existing node, ensure the new node has an action leading there.
3. Return a JSON object with a list of operations.

ACTION FORMAT (CRITICAL - follow this exactly):
Each action MUST have these fields:
- id: unique identifier (snake_case)
- text: display text shown to player (LLM uses this for intent matching)
- intent: optional natural-language behavior interpreted by the Architect
- effects: array of effect objects (optional when intent is provided)

EXAMPLE ACTION:
{
  "id": "go_to_armory",
  "text": "Enter the secret armory",
  "effects": [{"type": "goto_node", "target": "secret_armory"}]
}

OBJECT FORMAT (DSPP model):
Each object MUST have:
- id: unique identifier
- name: display name
- definition: static rules for LLM
- explicit_state: what player sees
- implicit_state: hidden AI context
- properties: key-value data
- interactions live in definition, not in a separate actions array

FORMAT:
{
  "isMultiOp": true,
  "operations": [
    {
      "operation": "update_node" | "create_node",
      "explanation": "Reason for change",
      "nodes": [ ... node objects ... ],
      "edges": [ ... edge objects ... ]
    }
  ]
}

IMPORTANT:
- When "converting" a pseudo node, use "update_node" with the SAME ID, but change its data to be a full node and its type will be handled by the editor (we will force type 'detailed').
- Ensure all JSON is valid.
- DO NOT use "label" for actions, use "text".
- Objects should not include an "actions" array.
- Use effects with type "goto_node" and "target" field for navigation.
`);

export const buildGenericAIPrompt = ({
    prompt,
    systemPrompt,
    contextData,
}) => appendEditorLanguageSection(`${systemPrompt}

CONTEXT DATA:
${JSON.stringify(contextData, null, 2)}

USER PROMPT:
${prompt}

INSTRUCTIONS:
Return a JSON object with the requested changes.
Format: { "operation": "update_...", "data": ... }
`);

/**
 * Submit prompt to LLM and apply changes
 */
export const handleLlmSubmit = async ({
    llmPrompt,
    nodes,
    edges,
    storyData,
    onSuccess,
    onError
}) => {
    if (!llmPrompt) return;

    try {
        // Get selected nodes
        const selectedNodes = nodes.filter(n => n.selected);

        // Build comprehensive prompt
        const prompt = buildPrompt(
            llmPrompt,
            selectedNodes,
            storyData || {},
            nodes,
            edges
        );

        console.log('Sending prompt to LLM...');

        // Call LLM API
        const response = await axios.post('/api/llm/generate', {
            prompt,
            model: 'llama3.2:latest'
        });

        console.log('LLM response:', response.data);

        // Extract result from response
        const result = response.data.result || response.data.response || response.data.suggestion || JSON.stringify(response.data);

        if (!result) {
            throw new Error('LLM returned empty response');
        }

        console.log('Parsing result:', result);

        // Parse and validate response
        const parsed = parseAIResponse(result);

        if (!parsed.success) {
            throw new Error(`AI Response Error:\n${parsed.error}`);
        }

        // Handle multi-operation or single operation
        if (parsed.data.isMultiOp) {
            // Multi-operation: apply sequentially
            let currentNodes = nodes;
            let currentEdges = edges;
            const explanations = [];

            for (const op of parsed.data.operations) {
                const result = applyAIChanges(
                    op.operation,
                    op.nodes,
                    op.edges,
                    { nodes: currentNodes, edges: currentEdges, storyData }
                );
                currentNodes = result.nodes;
                currentEdges = result.edges;
                explanations.push(`${op.operation}: ${op.explanation}`);
            }

            const stats = generateChangeSummary(parsed.data.operations);
            onSuccess(currentNodes, currentEdges, `✅ Changes applied!\n\n${stats}\n\nDetails:\n${explanations.join('\n')}`);
        } else {
            // Single operation
            const result = applyAIChanges(
                parsed.data.operation,
                parsed.data.nodes,
                parsed.data.edges,
                { nodes, edges, storyData }
            );

            onSuccess(result.nodes, result.edges, `✅ Changes applied!\n\n${parsed.data.operation}\n${parsed.data.explanation}`);
        }
    } catch (error) {
        console.error('LLM Error:', error);
        onError(error.message);
    }
};

/**
 * Batch convert pseudo-nodes to real nodes using LLM
 */
export const handleBatchConvert = async ({
    nodes,
    edges,
    storyData,
    viewMode,
    handleShapeClickFromNode,
    onSuccess,
    onError
}) => {
    const pseudoNodes = nodes.filter(n => n.type === 'pseudo');
    if (pseudoNodes.length === 0) return;

    try {
        // 1. Build Context
        const pseudoContext = pseudoNodes.map(n => `Pseudo-Node ID: ${n.id}\nPrompt: ${n.data.prompt}`).join('\n\n');

        // Find edges connected to pseudo nodes
        const relevantEdges = edges.filter(e =>
            pseudoNodes.some(n => n.id === e.source || n.id === e.target)
        );

        const edgeContext = relevantEdges.map(e => {
            const sourceNode = nodes.find(n => n.id === e.source);
            const targetNode = nodes.find(n => n.id === e.target);
            const sourceType = sourceNode.type === 'pseudo' ? 'Pseudo' : 'Real';
            const targetType = targetNode.type === 'pseudo' ? 'Pseudo' : 'Real';
            return `${sourceNode.id} (${sourceType}) -> ${targetNode.id} (${targetType})`;
        }).join('\n');

        // Find connected real nodes to provide context
        const connectedRealNodeIds = new Set();
        relevantEdges.forEach(e => {
            const sourceNode = nodes.find(n => n.id === e.source);
            const targetNode = nodes.find(n => n.id === e.target);
            if (sourceNode.type !== 'pseudo') connectedRealNodeIds.add(sourceNode.id);
            if (targetNode.type !== 'pseudo') connectedRealNodeIds.add(targetNode.id);
        });

        const realNodeContext = Array.from(connectedRealNodeIds).map(id => {
            const node = nodes.find(n => n.id === id);
            return `Existing Node ID: ${node.id}\nName: ${node.data.name}\nDescription: ${node.data.description}`;
        }).join('\n\n');

        const fullPrompt = buildBatchConvertPrompt({
            pseudoContext,
            edgeContext,
            realNodeContext,
        });

        console.log('Sending batch prompt:', fullPrompt);

        const response = await axios.post('/api/llm/generate', {
            prompt: fullPrompt,
            model: 'llama3.2:latest'
        });

        const result = response.data.result || response.data.response || response.data.suggestion || JSON.stringify(response.data);
        const parsed = parseAIResponse(result);

        if (!parsed.success) {
            throw new Error(`AI Response Error:\n${parsed.error}`);
        }

        if (parsed.data.isMultiOp) {
            let currentNodes = nodes;
            let currentEdges = edges;

            for (const op of parsed.data.operations) {
                const opNodes = op.nodes || [];

                const result = applyAIChanges(
                    op.operation,
                    op.nodes,
                    op.edges,
                    { nodes: currentNodes, edges: currentEdges, storyData }
                );

                // Post-process nodes to switch type from pseudo to detailed
                currentNodes = result.nodes.map(n => {
                    const wasPseudo = pseudoNodes.some(pn => pn.id === n.id);
                    const isTargeted = opNodes.some(on => on.id === n.id);
                    if (wasPseudo && isTargeted) {
                        return {
                            ...n,
                            type: viewMode === 'detailed' ? 'detailed' : 'default',
                            data: {
                                ...n.data,
                                onShapeClick: handleShapeClickFromNode
                            }
                        };
                    }
                    return n;
                });

                currentEdges = result.edges;
            }

            onSuccess(currentNodes, currentEdges);
        }
    } catch (error) {
        console.error("Batch generation error:", error);
        onError("Failed to generate nodes.");
    }
};
/**
 * Generic AI Generation for any context
 */
export const generateWithAI = async ({
    prompt,
    systemPrompt = "You are an AI assistant for the Wenyoo editor. Wenyoo is an AI native text based game engine.",
    contextData,
    model = 'llama3.2:latest'
}) => {
    const fullPrompt = buildGenericAIPrompt({
        prompt,
        systemPrompt,
        contextData,
    });

    console.log('Sending generic prompt:', fullPrompt);

    const response = await axios.post('/api/llm/generate', {
        prompt: fullPrompt,
        model
    });

    const result = response.data.result || response.data.response || JSON.stringify(response.data);
    return parseAIResponse(result); // Reuse parser if applicable or just return result
};

// =============================================================================
// NEW: Function Calling AI Edit with SSE Streaming
// =============================================================================

/**
 * AI Edit Sources - for distinguishing different loading states
 */
export const AI_SOURCES = {
    MAIN_GRAPH: 'main_graph',
    NODE_EDITOR: 'node_editor',
    CHARACTER_PANEL: 'character_panel',
    OBJECT_PANEL: 'object_panel',
    LORE_PANEL: 'lore_panel',
    PARAMETER_PANEL: 'parameter_panel',
    SECONDARY_EDITOR: 'secondary_editor'
};

/**
 * Editing modes - determines which tools are available
 */
export const EDIT_MODES = {
    NODES: 'nodes',
    CHARACTERS: 'characters',
    OBJECTS: 'objects',
    PARAMETERS: 'parameters',
    STORY_CREATION: 'story_creation',  // Full story creation with all tools
    ALL: 'all'
};

/**
 * SSE Event Types from the backend
 */
export const SSE_EVENTS = {
    THINKING: 'thinking',
    FUNCTION_CALL: 'function_call',
    // Node events
    NODE_CREATED: 'node_created',
    NODE_UPDATED: 'node_updated',
    NODE_DELETED: 'node_deleted',
    EDGE_CREATED: 'edge_created',
    EDGE_DELETED: 'edge_deleted',
    OBJECT_ADDED: 'object_added',
    // Character events
    CHARACTER_CREATED: 'character_created',
    CHARACTER_UPDATED: 'character_updated',
    CHARACTER_DELETED: 'character_deleted',
    // Global object events
    GLOBAL_OBJECT_CREATED: 'global_object_created',
    GLOBAL_OBJECT_UPDATED: 'global_object_updated',
    GLOBAL_OBJECT_DELETED: 'global_object_deleted',
    // Parameter events
    PARAMETER_SET: 'parameter_set',
    PARAMETER_DELETED: 'parameter_deleted',
    // General
    ERROR: 'error',
    COMPLETE: 'complete'
};

/**
 * Convert backend node format to ReactFlow node format
 */
const toReactFlowNode = (nodeData, position = null, viewMode = 'detailed') => {
    // Defensive check for undefined/null nodeData
    if (!nodeData) {
        console.warn('[toReactFlowNode] Received undefined nodeData');
        return null;
    }
    
    const nodeId = nodeData.id || `node-${Date.now()}`;
    return {
        id: nodeId,
        type: viewMode === 'detailed' ? 'detailed' : 'default',
        data: {
            ...nodeData,
            id: nodeId,
            label: nodeData.name || nodeId,
            viewMode
        },
        position: position || { x: 100, y: 100 }
    };
};

/**
 * Convert backend edge format to ReactFlow edge format
 */
const toReactFlowEdge = (edgeData) => {
    // Defensive check for undefined/null edgeData
    if (!edgeData || !edgeData.source || !edgeData.target) {
        console.warn('[toReactFlowEdge] Received invalid edgeData:', edgeData);
        return null;
    }
    
    return {
        id: edgeData.id || `edge-${edgeData.source}-${edgeData.target}-${Date.now()}`,
        source: edgeData.source,
        target: edgeData.target,
        label: edgeData.label || '',
        labelStyle: { fill: '#374151', fontWeight: 500, fontSize: 12 },
        labelBgStyle: { fill: 'white', fillOpacity: 0.9 },
        labelBgPadding: [8, 4],
        labelBgBorderRadius: 4,
        markerEnd: { type: 'arrowclosed' },
        animated: true
    };
};

/**
 * Stream AI edits with real-time updates via SSE
 * 
 * This uses the new function-calling approach where the LLM makes
 * structured tool calls that are executed on the backend.
 * Changes are streamed in real-time so the UI updates as the AI works.
 * 
 * Supports multiple modes:
 * - nodes: Edit story nodes and edges
 * - characters: Edit NPCs and playable characters
 * - objects: Edit global object definitions
 * - parameters: Edit initial_variables/parameters
 * - all: Access to all tools
 * 
 * @param {Object} options
 * @param {string} options.prompt - User's edit request
 * @param {string} options.mode - EDIT_MODES value (nodes, characters, objects, parameters, all)
 * @param {Array} options.nodes - Current ReactFlow nodes (for node mode)
 * @param {Array} options.edges - Current ReactFlow edges (for node mode)
 * @param {Array} options.characters - Current characters (for character mode)
 * @param {Array} options.objects - Current global objects (for object mode)
 * @param {Object} options.parameters - Current parameters (for parameter mode)
 * @param {Object} options.storyData - Story metadata and analysis
 * @param {string} options.source - AI_SOURCES value for UI distinction
 * @param {string} options.viewMode - Current view mode ('detailed' or 'default')
 * @param {Function} options.onThinking - Called when AI is processing
 * @param {Function} options.onFunctionCall - Called when AI calls a function
 * @param {Function} options.onNodeCreated - Called when a node is created
 * @param {Function} options.onNodeUpdated - Called when a node is updated
 * @param {Function} options.onNodeDeleted - Called when a node is deleted
 * @param {Function} options.onEdgeCreated - Called when an edge is created
 * @param {Function} options.onEdgeDeleted - Called when an edge is deleted
 * @param {Function} options.onCharacterCreated - Called when a character is created
 * @param {Function} options.onCharacterUpdated - Called when a character is updated
 * @param {Function} options.onCharacterDeleted - Called when a character is deleted
 * @param {Function} options.onObjectCreated - Called when a global object is created
 * @param {Function} options.onObjectUpdated - Called when a global object is updated
 * @param {Function} options.onObjectDeleted - Called when a global object is deleted
 * @param {Function} options.onParameterSet - Called when a parameter is set
 * @param {Function} options.onParameterDeleted - Called when a parameter is deleted
 * @param {Function} options.onComplete - Called when all changes are done
 * @param {Function} options.onError - Called on error
 */
export const streamAIEdit = async ({
    prompt,
    mode = EDIT_MODES.NODES,
    nodes = [],
    edges = [],
    characters = [],
    objects = [],
    parameters = {},
    storyData,
    source = AI_SOURCES.MAIN_GRAPH,
    viewMode = 'detailed',
    onThinking,
    onFunctionCall,
    onNodeCreated,
    onNodeUpdated,
    onNodeDeleted,
    onEdgeCreated,
    onEdgeDeleted,
    onCharacterCreated,
    onCharacterUpdated,
    onCharacterDeleted,
    onObjectCreated,
    onObjectUpdated,
    onObjectDeleted,
    onParameterSet,
    onParameterDeleted,
    onComplete,
    onError
}) => {
    if (!prompt) {
        onError?.('Prompt is required');
        return;
    }

    // Prepare payload with all entity types
    const payload = {
        prompt,
        mode,
        // Nodes (convert from ReactFlow format)
        nodes: nodes.map(n => ({
            id: n.id,
            ...n.data
        })),
        edges: edges.map(e => ({
            id: e.id,
            source: e.source,
            target: e.target,
            label: e.label || ''
        })),
        // Characters, objects, parameters (already in correct format)
        characters,
        objects,
        parameters,
        // Context
        context: {
            storyData,
            source
        }
    };

    try {
        console.log('[AI Stream] Starting SSE connection...');
        
        const response = await editorFetch('/api/editor/ai-edit-stream', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`HTTP ${response.status}: ${errorText}`);
        }

        // Check if response is SSE stream
        const contentType = response.headers.get('content-type');
        if (!contentType?.includes('text/event-stream')) {
            // Fallback: response is JSON (error)
            const jsonResponse = await response.json();
            if (jsonResponse.error) {
                throw new Error(jsonResponse.error);
            }
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let currentEventType = null;  // Moved outside loop to persist across chunks

        // Helper function to process a single line
        const processLine = (line) => {
            if (line.startsWith('event: ')) {
                currentEventType = line.slice(7).trim();
            } else if (line.startsWith('data: ') && currentEventType) {
                try {
                    const data = JSON.parse(line.slice(6));
                    
                    console.log(`[AI Stream] Event: ${currentEventType}`, data);

                    // Dispatch to appropriate handler
                    switch (currentEventType) {
                        case SSE_EVENTS.THINKING:
                            onThinking?.(data.message);
                            break;

                        case SSE_EVENTS.FUNCTION_CALL:
                            onFunctionCall?.(data.function, data.arguments);
                            break;

                        // ====== NODE EVENTS ======
                        case SSE_EVENTS.NODE_CREATED: {
                            const rfNode = toReactFlowNode(
                                data.node,
                                data.position,
                                viewMode
                            );
                            if (rfNode) {
                                const rfEdges = (data.edges || []).map(toReactFlowEdge).filter(Boolean);
                                onNodeCreated?.(rfNode, rfEdges);
                            }
                            break;
                        }

                        case SSE_EVENTS.NODE_UPDATED: {
                            if (data.node) {
                                onNodeUpdated?.(data.node, data.updated_fields, 
                                    (data.new_edges || []).map(toReactFlowEdge).filter(Boolean));
                            }
                            break;
                        }

                        case SSE_EVENTS.NODE_DELETED:
                            onNodeDeleted?.(data.node_id);
                            break;

                        case SSE_EVENTS.EDGE_CREATED: {
                            const rfEdge = toReactFlowEdge(data);
                            if (rfEdge) {
                                onEdgeCreated?.(rfEdge);
                            }
                            break;
                        }

                        case SSE_EVENTS.EDGE_DELETED:
                            onEdgeDeleted?.(data.id || `${data.source}-${data.target}`);
                            break;

                        case SSE_EVENTS.OBJECT_ADDED:
                            onNodeUpdated?.({ id: data.node_id, objects: [data.object] }, 
                                ['objects'], 
                                (data.new_edges || []).map(toReactFlowEdge));
                            break;

                        // ====== CHARACTER EVENTS ======
                        case SSE_EVENTS.CHARACTER_CREATED:
                            onCharacterCreated?.(data.character);
                            break;

                        case SSE_EVENTS.CHARACTER_UPDATED:
                            onCharacterUpdated?.(data.character, data.updated_fields);
                            break;

                        case SSE_EVENTS.CHARACTER_DELETED:
                            onCharacterDeleted?.(data.character_id);
                            break;

                        // ====== GLOBAL OBJECT EVENTS ======
                        case SSE_EVENTS.GLOBAL_OBJECT_CREATED:
                            onObjectCreated?.(data.object);
                            break;

                        case SSE_EVENTS.GLOBAL_OBJECT_UPDATED:
                            onObjectUpdated?.(data.object, data.updated_fields);
                            break;

                        case SSE_EVENTS.GLOBAL_OBJECT_DELETED:
                            onObjectDeleted?.(data.object_id);
                            break;

                        // ====== PARAMETER EVENTS ======
                        case SSE_EVENTS.PARAMETER_SET:
                            onParameterSet?.(data.key, data.value, data.is_new);
                            break;

                        case SSE_EVENTS.PARAMETER_DELETED:
                            onParameterDeleted?.(data.key);
                            break;

                        // ====== GENERAL EVENTS ======
                        case SSE_EVENTS.COMPLETE:
                            onComplete?.({
                                message: data.message,
                                summary: data.summary,
                                finalState: data.final_state
                            });
                            break;

                        case SSE_EVENTS.ERROR:
                            onError?.(data.error);
                            break;

                        default:
                            console.warn(`[AI Stream] Unknown event type: ${currentEventType}`);
                    }
                } catch (parseError) {
                    console.error('[AI Stream] Failed to parse event data:', parseError, line);
                }

                currentEventType = null;
            }
        };

        while (true) {
            const { done, value } = await reader.read();
            if (done) {
                console.log('[AI Stream] Stream ended');
                break;
            }

            buffer += decoder.decode(value, { stream: true });

            // Parse SSE events from buffer
            const lines = buffer.split('\n');
            buffer = lines.pop() || ''; // Keep incomplete line in buffer

            for (const line of lines) {
                processLine(line);
            }
        }
        
        // Process any remaining content in the buffer after stream ends
        if (buffer.trim()) {
            const remainingLines = buffer.split('\n');
            for (const line of remainingLines) {
                processLine(line);
            }
        }
    } catch (error) {
        console.error('[AI Stream] Error:', error);
        onError?.(error.message);
    }
};

/**
 * Calculate a good position for a new node in the graph
 */
export const calculateNewNodePosition = (existingNodes, basePosition = null) => {
    if (basePosition) {
        return basePosition;
    }

    // Find the rightmost and bottom-most positions
    let maxX = 100;
    let maxY = 100;

    existingNodes.forEach(node => {
        if (node.position) {
            maxX = Math.max(maxX, node.position.x);
            maxY = Math.max(maxY, node.position.y);
        }
    });

    // Position new node to the right of existing content
    return {
        x: maxX + 350,
        y: 100 + (existingNodes.length % 4) * 200
    };
};

// =============================================================================
// PLAN-BASED AI EDITING
// =============================================================================

/**
 * Plan types for the execution plan
 */
export const PLAN_TYPES = {
    STORY_CREATION: 'story_creation',
    STORY_MODIFICATION: 'story_modification',
    NODE_EXPANSION: 'node_expansion',
    OUTLINE_REFINEMENT: 'outline_refinement'
};

/**
 * Plan scope - what parts of the story will be affected
 */
export const PLAN_SCOPES = {
    FULL_STORY: 'full_story',
    SELECTED_NODES: 'selected_nodes',
    SINGLE_NODE: 'single_node',
    PARAMETERS_ONLY: 'parameters_only'
};

/**
 * Generate an execution plan for the user's request.
 * 
 * This is the first phase of the plan-based approach. The LLM analyzes
 * the request and generates a structured plan that can be reviewed
 * before execution.
 * 
 * @param {Object} options
 * @param {string} options.prompt - User's edit request
 * @param {Array} options.nodes - Current ReactFlow nodes
 * @param {Array} options.edges - Current ReactFlow edges
 * @param {Array} options.characters - Current characters
 * @param {Array} options.objects - Current objects
 * @param {Object} options.parameters - Current parameters
 * @param {Array} options.selectedNodeIds - IDs of selected nodes
 * @param {Object} options.storyMetadata - Story metadata
 * @returns {Promise<Object>} The generated plan
 */
export const generatePlan = async ({
    prompt,
    nodes = [],
    edges = [],
    characters = [],
    objects = [],
    parameters = {},
    selectedNodeIds = [],
    storyMetadata = {}
}) => {
    const response = await editorFetch('/api/editor/generate-plan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            prompt,
            nodes: nodes.map(n => ({ id: n.id, ...n.data })),
            edges: edges.map(e => ({ id: e.id, source: e.source, target: e.target, label: e.label })),
            characters,
            objects,
            parameters,
            selected_node_ids: selectedNodeIds,
            story_metadata: storyMetadata
        })
    });
    
    const result = await response.json();
    if (!response.ok || result.error) {
        throw new Error(result.error || 'Failed to generate plan');
    }
    
    return result.plan;
};

/**
 * Execute a plan with SSE streaming for real-time updates.
 * 
 * This is the second phase - executing the plan step by step.
 * No LLM calls are made during execution, just deterministic operations.
 * 
 * @param {Object} options
 * @param {Object} options.plan - The execution plan to run
 * @param {Array} options.nodes - Current ReactFlow nodes
 * @param {Array} options.edges - Current ReactFlow edges
 * @param {Array} options.characters - Current characters
 * @param {Array} options.objects - Current objects
 * @param {Object} options.parameters - Current parameters
 * @param {string} options.viewMode - Current view mode
 * @param {Function} options.onThinking - Progress callback
 * @param {Function} options.onNodeCreated - Node created callback
 * @param {Function} options.onNodeUpdated - Node updated callback
 * @param {Function} options.onNodeDeleted - Node deleted callback
 * @param {Function} options.onEdgeCreated - Edge created callback
 * @param {Function} options.onCharacterCreated - Character created callback
 * @param {Function} options.onCharacterUpdated - Character updated callback
 * @param {Function} options.onObjectCreated - Object created callback
 * @param {Function} options.onParameterSet - Parameter set callback
 * @param {Function} options.onComplete - Completion callback
 * @param {Function} options.onError - Error callback
 */
export const executePlan = async ({
    plan,
    nodes = [],
    edges = [],
    characters = [],
    objects = [],
    parameters = {},
    viewMode = 'detailed',
    onThinking,
    onNodeCreated,
    onNodeUpdated,
    onNodeDeleted,
    onEdgeCreated,
    onEdgeDeleted,
    onCharacterCreated,
    onCharacterUpdated,
    onCharacterDeleted,
    onObjectCreated,
    onObjectUpdated,
    onObjectDeleted,
    onParameterSet,
    onParameterDeleted,
    onComplete,
    onError
}) => {
    try {
        const response = await editorFetch('/api/editor/execute-plan', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                plan,
                nodes: nodes.map(n => ({ id: n.id, ...n.data })),
                edges: edges.map(e => ({ id: e.id, source: e.source, target: e.target, label: e.label })),
                characters,
                objects,
                parameters
            })
        });
        
        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`HTTP ${response.status}: ${errorText}`);
        }
        
        // Process SSE stream (same as streamAIEdit)
        await processSSEStream(response, {
            viewMode,
            onThinking,
            onNodeCreated,
            onNodeUpdated,
            onNodeDeleted,
            onEdgeCreated,
            onEdgeDeleted,
            onCharacterCreated,
            onCharacterUpdated,
            onCharacterDeleted,
            onObjectCreated,
            onObjectUpdated,
            onObjectDeleted,
            onParameterSet,
            onParameterDeleted,
            onComplete,
            onError
        });
    } catch (error) {
        console.error('[Plan Execute] Error:', error);
        onError?.(error.message);
    }
};

/**
 * Quick generate: Generate plan and execute in one step.
 * 
 * For simpler requests where plan review isn't needed.
 * 
 * @param {Object} options - Same as executePlan plus prompt
 */
export const quickGenerate = async ({
    prompt,
    nodes = [],
    edges = [],
    characters = [],
    objects = [],
    parameters = {},
    selectedNodeIds = [],
    storyMetadata = {},
    viewMode = 'detailed',
    onThinking,
    onPlanReady,
    onNodeCreated,
    onNodeUpdated,
    onNodeDeleted,
    onEdgeCreated,
    onEdgeDeleted,
    onCharacterCreated,
    onCharacterUpdated,
    onCharacterDeleted,
    onObjectCreated,
    onObjectUpdated,
    onObjectDeleted,
    onParameterSet,
    onParameterDeleted,
    onComplete,
    onError
}) => {
    try {
        const response = await editorFetch('/api/editor/quick-generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                prompt,
                nodes: nodes.map(n => ({ id: n.id, ...n.data })),
                edges: edges.map(e => ({ id: e.id, source: e.source, target: e.target, label: e.label })),
                characters,
                objects,
                parameters,
                selected_node_ids: selectedNodeIds,
                story_metadata: storyMetadata
            })
        });
        
        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`HTTP ${response.status}: ${errorText}`);
        }
        
        await processSSEStream(response, {
            viewMode,
            onThinking: (message, data) => {
                // Check if this is the plan ready event
                if (data?.plan_summary) {
                    onPlanReady?.(data.plan_summary);
                }
                onThinking?.(message);
            },
            onNodeCreated,
            onNodeUpdated,
            onNodeDeleted,
            onEdgeCreated,
            onEdgeDeleted,
            onCharacterCreated,
            onCharacterUpdated,
            onCharacterDeleted,
            onObjectCreated,
            onObjectUpdated,
            onObjectDeleted,
            onParameterSet,
            onParameterDeleted,
            onComplete,
            onError
        });
    } catch (error) {
        console.error('[Quick Generate] Error:', error);
        onError?.(error.message);
    }
};

/**
 * Generate story outline options for the creation wizard.
 * 
 * @param {string} idea - User's initial story idea
 * @param {number} numOptions - Number of options to generate
 * @returns {Promise<Array>} Array of outline options
 */
export const generateOutlines = async (idea, numOptions = 3) => {
    const response = await editorFetch('/api/editor/generate-outlines', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ idea, num_options: numOptions })
    });
    
    const result = await response.json();
    if (!response.ok || result.error) {
        throw new Error(result.error || 'Failed to generate outlines');
    }
    
    return result.outlines;
};

/**
 * Generate outline options from a normalized import draft plus writer intent.
 *
 * @param {Object} importDraft - Normalized imported source material
 * @param {string} writerIntent - What the writer wants to create from the source
 * @param {number} numOptions - Number of options to generate
 * @returns {Promise<Array>} Array of outline options
 */
export const generateImportOutlines = async (importDraft, writerIntent, numOptions = 3) => {
    const response = await editorFetch('/api/editor/import/generate-outlines', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            import_draft: importDraft,
            writer_intent: writerIntent,
            num_options: numOptions
        })
    });

    const result = await response.json();
    if (!response.ok || result.error) {
        throw new Error(result.error || 'Failed to generate import outlines');
    }

    return result.outlines;
};

/**
 * Prepare a single reviewable conversion draft from imported source material.
 *
 * @param {Object} importDraft - Normalized imported source material
 * @param {string} writerIntent - What the writer wants to create from the source
 * @returns {Promise<Object>} Detailed outline and execution plan
 */
export const prepareImportConversion = async (importDraft, writerIntent) => {
    const response = await editorFetch('/api/editor/import/prepare-conversion', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            import_draft: importDraft,
            writer_intent: writerIntent
        })
    });

    const result = await response.json();
    if (!response.ok || result.error) {
        throw new Error(result.error || 'Failed to prepare import conversion');
    }

    return {
        detailedOutline: result.detailed_outline,
        loreOutline: result.lore_outline,
        plan: result.plan
    };
};

/**
 * Expand a selected outline into detailed structure with execution plan.
 * 
 * @param {Object} outline - The selected outline
 * @param {string} modifications - User's requested modifications (optional)
 * @returns {Promise<Object>} Detailed outline and execution plan
 */
export const expandOutline = async (outline, modifications = null) => {
    const response = await editorFetch('/api/editor/expand-outline', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ outline, modifications })
    });
    
    const result = await response.json();
    if (!response.ok || result.error) {
        throw new Error(result.error || 'Failed to expand outline');
    }
    
    return {
        detailedOutline: result.detailed_outline,
        loreOutline: result.lore_outline,
        plan: result.plan
    };
};

/**
 * Expand an import-derived outline into a detailed structure and execution plan.
 *
 * @param {Object} importDraft - Normalized imported source material
 * @param {Object} outline - The selected outline
 * @param {string} modifications - Optional user-requested changes
 * @returns {Promise<Object>} Detailed outline and execution plan
 */
export const expandImportOutline = async (importDraft, outline, modifications = null) => {
    const response = await editorFetch('/api/editor/import/expand-outline', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            import_draft: importDraft,
            outline,
            modifications
        })
    });

    const result = await response.json();
    if (!response.ok || result.error) {
        throw new Error(result.error || 'Failed to expand import outline');
    }

    return {
        detailedOutline: result.detailed_outline,
        loreOutline: result.lore_outline,
        plan: result.plan
    };
};

/**
 * Refine a single outline based on user feedback.
 * Used for AI-assisted modifications to individual direction cards.
 * 
 * @param {Object} outline - The current outline to refine
 * @param {string} feedback - User's modification request
 * @returns {Promise<Object>} The refined outline
 */
export const refineOutline = async (outline, feedback) => {
    const response = await editorFetch('/api/editor/refine-outline', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ outline, feedback })
    });
    
    const result = await response.json();
    if (!response.ok || result.error) {
        throw new Error(result.error || 'Failed to refine outline');
    }
    
    return result.refined_outline;
};

/**
 * Refine the current set of outline directions in place.
 *
 * @param {Array} outlines - Current outline options
 * @param {string} feedback - User's modification request
 * @param {number|null} selectedIndex - Currently selected outline index
 * @returns {Promise<Object>} Updated outlines and suggested selection
 */
export const refineOutlines = async (outlines, feedback, selectedIndex = null) => {
    const response = await editorFetch('/api/editor/refine-outlines', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            outlines,
            feedback,
            selected_index: selectedIndex
        })
    });

    const result = await response.json();
    if (!response.ok || result.error) {
        throw new Error(result.error || 'Failed to refine outlines');
    }

    return {
        outlines: result.updated_outlines || [],
        selectedIndex: typeof result.selected_index === 'number' ? result.selected_index : selectedIndex
    };
};

/**
 * Refine the current detailed outline and regenerate the plan in place.
 *
 * @param {Object} detailedOutline - Current detailed outline
 * @param {string} feedback - User's modification request
 * @returns {Promise<Object>} Updated detailed outline and plan
 */
export const refineDetailedOutline = async (detailedOutline, feedback) => {
    const response = await editorFetch('/api/editor/refine-detailed-outline', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            detailed_outline: detailedOutline,
            feedback
        })
    });

    const result = await response.json();
    if (!response.ok || result.error) {
        throw new Error(result.error || 'Failed to refine detailed outline');
    }

    return {
        detailedOutline: result.detailed_outline,
        loreOutline: result.lore_outline,
        plan: result.plan
    };
};

/**
 * Conductor event types from the backend.
 */
const CONDUCTOR_EVENTS = {
    PHASE_START: 'phase_start',
    NODE_EXPANDING: 'node_expanding',
    NODE_COMPLETE: 'node_complete',
    NODE_ERROR: 'node_error',
    CHARACTER_PLACING: 'character_placing',
    CHARACTER_PLACED: 'character_placed',
    CONNECTIONS_CREATING: 'connections_creating',
    COMPLETE: 'complete',
    ERROR: 'error'
};

/**
 * Conduct story generation: expand skeleton into complete story using parallel LLM calls.
 * 
 * @param {Object} skeleton - The skeleton story structure from execute-plan
 * @param {Object} detailedOutline - The detailed outline with story structure
 * @param {Object} handlers - Event handlers for streaming updates
 * @param {number} maxConcurrent - Maximum parallel LLM calls (default: 3)
 */
export const conductStory = async (skeleton, detailedOutline, handlers, maxConcurrent = 3) => {
    const {
        onPhaseStart,
        onNodeExpanding,
        onNodeComplete,
        onNodeError,
        onCharacterPlaced,
        onConnectionsCreating,
        onComplete,
        onError
    } = handlers;
    
    try {
        const response = await editorFetch('/api/editor/conduct-story', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                skeleton,
                detailed_outline: detailedOutline,
                max_concurrent: maxConcurrent
            })
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to start story conducting');
        }
        
        // Process SSE stream
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let finalStoryResult = null;
        
        // Helper function to process a single line
        const processLine = (line) => {
            if (!line.startsWith('data: ')) return;
            
            try {
                const data = JSON.parse(line.slice(6));
                const eventType = data.type;
                
                switch (eventType) {
                    case CONDUCTOR_EVENTS.PHASE_START:
                        onPhaseStart?.(data.phase, data.message, data);
                        break;
                        
                    case CONDUCTOR_EVENTS.NODE_EXPANDING:
                        onNodeExpanding?.(data.node_id, data.node_name, data.progress);
                        break;
                        
                    case CONDUCTOR_EVENTS.NODE_COMPLETE:
                        onNodeComplete?.(data.node_id, data.node_name, {
                            actionsCount: data.actions_count,
                            objectsCount: data.objects_count,
                            nodeData: data.node_data,
                            progress: data.progress
                        });
                        break;
                        
                    case CONDUCTOR_EVENTS.NODE_ERROR:
                        onNodeError?.(data.node_id, data.error);
                        break;
                        
                    case CONDUCTOR_EVENTS.CHARACTER_PLACED:
                        onCharacterPlaced?.(data.character_id, data.node_id);
                        break;
                        
                    case CONDUCTOR_EVENTS.CONNECTIONS_CREATING:
                        onConnectionsCreating?.(data.connections_count);
                        break;
                        
                    case CONDUCTOR_EVENTS.COMPLETE:
                        onComplete?.({
                            message: data.message,
                            nodesExpanded: data.nodes_expanded,
                            errors: data.errors,
                            finalStory: data.final_story
                        });
                        finalStoryResult = data.final_story;
                        break;
                        
                    case CONDUCTOR_EVENTS.ERROR:
                        onError?.(data.error);
                        throw new Error(data.error);
                }
            } catch (parseError) {
                // Only log actual parse errors, not end-of-stream issues
                if (parseError.message && 
                    !parseError.message.includes('Unexpected end of JSON input') &&
                    !parseError.message.includes('Unexpected token')) {
                    console.error('[Conductor SSE] Parse error:', parseError, line);
                    // Re-throw actual processing errors
                    if (parseError.message.includes('conductor') || parseError.message.includes('story')) {
                        throw parseError;
                    }
                }
            }
        };
        
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            buffer += decoder.decode(value, { stream: true });
            
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';
            
            for (const line of lines) {
                processLine(line);
                if (finalStoryResult) {
                    return finalStoryResult;
                }
            }
        }
        
        // Process any remaining content in the buffer after stream ends
        if (buffer.trim()) {
            const remainingLines = buffer.split('\n');
            for (const line of remainingLines) {
                processLine(line);
            }
        }
        
        return finalStoryResult;
    } catch (error) {
        onError?.(error.message);
        throw error;
    }
};

/**
 * Execute the full story creation flow: expand outline, execute plan, then conduct.
 * This combines the skeleton creation and node expansion into a single streaming operation.
 * 
 * @param {Object} outline - The selected outline
 * @param {string} modifications - Optional modifications
 * @param {Object} handlers - Event handlers for all phases
 * @returns {Promise<Object>} The final complete story
 */
export const createCompleteStory = async (outline, modifications, handlers) => {
    const {
        onExpandStart,
        onExpandComplete,
        onExecuteStart,
        onExecuteProgress,
        onConductStart,
        onConductProgress,
        onComplete,
        onError
    } = handlers;
    
    try {
        // Phase 1: Expand outline to get detailed structure and plan
        onExpandStart?.();
        const { detailedOutline, loreOutline, plan } = await expandOutline(outline, modifications);
        onExpandComplete?.(detailedOutline, plan);
        
        // Phase 2: Execute the skeleton plan
        onExecuteStart?.();
        const skeletonResult = await new Promise((resolve, reject) => {
            executePlan({
                plan,
                nodes: [],
                edges: [],
                characters: [],
                objects: [],
                parameters: {},
                onThinking: (msg) => onExecuteProgress?.('thinking', msg),
                onNodeCreated: (node) => onExecuteProgress?.('node_created', node),
                onCharacterCreated: (char) => onExecuteProgress?.('character_created', char),
                onObjectCreated: (obj) => onExecuteProgress?.('object_created', obj),
                onParameterSet: (key, value) => onExecuteProgress?.('parameter_set', { key, value }),
                onComplete: (result) => resolve(result),
                onError: (error) => reject(new Error(error))
            });
        });
        
        // Build skeleton from the result
        const skeleton = skeletonResult.finalState || {};
        
        // Phase 3: Conduct - expand nodes with LLM
        onConductStart?.();
        const finalStory = await conductStory(skeleton, detailedOutline, {
            onPhaseStart: (phase, msg) => onConductProgress?.('phase', { phase, message: msg }),
            onNodeExpanding: (nodeId, nodeName, progress) => 
                onConductProgress?.('expanding', { nodeId, nodeName, progress }),
            onNodeComplete: (nodeId, nodeName, info) => 
                onConductProgress?.('complete', { nodeId, nodeName, ...info }),
            onNodeError: (nodeId, error) => 
                onConductProgress?.('error', { nodeId, error }),
            onComplete: (result) => onComplete?.(result),
            onError: (error) => { throw new Error(error); }
        });
        
        return finalStory;
        
    } catch (error) {
        onError?.(error.message);
        throw error;
    }
};

/**
 * Process SSE stream from the server.
 * Shared by executePlan and quickGenerate.
 */
const processSSEStream = async (response, handlers) => {
    const {
        viewMode = 'detailed',
        onThinking,
        onNodeCreated,
        onNodeUpdated,
        onNodeDeleted,
        onEdgeCreated,
        onEdgeDeleted,
        onCharacterCreated,
        onCharacterUpdated,
        onCharacterDeleted,
        onObjectCreated,
        onObjectUpdated,
        onObjectDeleted,
        onParameterSet,
        onParameterDeleted,
        onComplete,
        onError
    } = handlers;
    
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let currentEventType = null;  // Moved outside loop to persist across chunks
    
    // Helper function to process a single line
    const processLine = (line) => {
        if (line.startsWith('event: ')) {
            currentEventType = line.slice(7).trim();
        } else if (line.startsWith('data: ') && currentEventType) {
            try {
                const data = JSON.parse(line.slice(6));
                
                switch (currentEventType) {
                    case SSE_EVENTS.THINKING:
                        onThinking?.(data.message, data);
                        break;
                        
                    case SSE_EVENTS.NODE_CREATED: {
                        const rfNode = toReactFlowNode(data.node, data.position, viewMode);
                        if (rfNode) {
                            const rfEdges = (data.edges || []).map(toReactFlowEdge).filter(Boolean);
                            onNodeCreated?.(rfNode, rfEdges);
                        }
                        break;
                    }
                    
                    case SSE_EVENTS.NODE_UPDATED:
                        if (data.node) {
                            onNodeUpdated?.(data.node, data.updated_fields,
                                (data.new_edges || []).map(toReactFlowEdge).filter(Boolean));
                        }
                        break;
                        
                    case SSE_EVENTS.NODE_DELETED:
                        onNodeDeleted?.(data.node_id);
                        break;
                        
                    case SSE_EVENTS.EDGE_CREATED: {
                        const rfEdge = toReactFlowEdge(data);
                        if (rfEdge) {
                            onEdgeCreated?.(rfEdge);
                        }
                        break;
                    }
                        
                    case SSE_EVENTS.EDGE_DELETED:
                        onEdgeDeleted?.(data.id || `${data.source}-${data.target}`);
                        break;
                        
                    case SSE_EVENTS.CHARACTER_CREATED:
                        onCharacterCreated?.(data.character);
                        break;
                        
                    case SSE_EVENTS.CHARACTER_UPDATED:
                        onCharacterUpdated?.(data.character, data.updated_fields);
                        break;
                        
                    case SSE_EVENTS.CHARACTER_DELETED:
                        onCharacterDeleted?.(data.character_id);
                        break;
                        
                    case SSE_EVENTS.GLOBAL_OBJECT_CREATED:
                        onObjectCreated?.(data.object);
                        break;
                        
                    case SSE_EVENTS.GLOBAL_OBJECT_UPDATED:
                        onObjectUpdated?.(data.object, data.updated_fields);
                        break;
                        
                    case SSE_EVENTS.GLOBAL_OBJECT_DELETED:
                        onObjectDeleted?.(data.object_id);
                        break;
                        
                    case SSE_EVENTS.PARAMETER_SET:
                        onParameterSet?.(data.key, data.value, data.is_new);
                        break;
                        
                    case SSE_EVENTS.PARAMETER_DELETED:
                        onParameterDeleted?.(data.key);
                        break;
                        
                    case SSE_EVENTS.COMPLETE:
                        onComplete?.({
                            message: data.message,
                            summary: data.summary,
                            finalState: data.final_state
                        });
                        break;
                        
                    case SSE_EVENTS.ERROR:
                        onError?.(data.error);
                        break;
                }
            } catch (parseError) {
                console.error('[SSE] Parse error:', parseError, line);
            }
            
            currentEventType = null;
        }
    };
    
    while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        
        buffer += decoder.decode(value, { stream: true });
        
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        
        for (const line of lines) {
            processLine(line);
        }
    }
    
    // Process any remaining content in the buffer after stream ends
    if (buffer.trim()) {
        const remainingLines = buffer.split('\n');
        for (const line of remainingLines) {
            processLine(line);
        }
    }
};

// ============================================================================
// STORY REVIEW AND VALIDATION
// ============================================================================

/**
 * Review a complete story for structural, reference, numerical, and quality issues.
 * 
 * @param {Object} story - The complete story data (nodes, characters, objects, etc.)
 * @param {boolean} includeLlmAnalysis - Whether to use LLM for deeper analysis
 * @returns {Promise<Object>} Review report with issues and recommendations
 */
export const reviewStory = async (story, includeLlmAnalysis = false) => {
    try {
        const response = await editorFetch('/api/editor/review-story', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                story,
                include_llm_analysis: includeLlmAnalysis
            })
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `Review failed: ${response.status}`);
        }

        return await response.json();
    } catch (error) {
        console.error('[Review] Error:', error);
        throw error;
    }
};

/**
 * Quick validation for real-time editing feedback.
 * 
 * @param {string} nodeId - ID of the node being edited
 * @param {Object} nodeData - Current node data
 * @param {Object} context - Optional context (adjacent nodes, etc.)
 * @returns {Promise<Object>} Quick validation result
 */
export const validateNodeQuick = async (nodeId, nodeData, context = {}) => {
    try {
        const response = await editorFetch('/api/editor/validate-quick', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                node_id: nodeId,
                node_data: nodeData,
                context
            })
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `Validation failed: ${response.status}`);
        }

        return await response.json();
    } catch (error) {
        console.error('[Validation] Error:', error);
        throw error;
    }
};

/**
 * Convert story editor state to story format for review.
 * 
 * @param {Object} editorState - Current editor state
 * @returns {Object} Story formatted for review API
 */
export const editorStateToStory = (editorState) => {
    const { nodes, edges, characters, objects, parameters } = editorState;
    
    // Convert ReactFlow nodes to story nodes format
    const storyNodes = {};
    nodes.forEach(node => {
        const nodeData = node.data || {};
        storyNodes[node.id] = {
            id: node.id,
            name: nodeData.name || nodeData.label || node.id,
            description: nodeData.description || nodeData.explicit_state || '',
            actions: nodeData.actions || [],
            objects: nodeData.objects || [],
            triggers: nodeData.triggers || [],
            isStartNode: nodeData.isStartNode || false,
            is_ending: nodeData.is_ending || nodeData.isEnding || false
        };
    });
    
    // Find start node
    let startNodeId = null;
    for (const nodeId in storyNodes) {
        if (storyNodes[nodeId].isStartNode) {
            startNodeId = nodeId;
            break;
        }
    }
    
    return {
        nodes: storyNodes,
        characters: characters || [],
        objects: objects || [],
        initial_variables: parameters || {},
        start_node_id: startNodeId
    };
};

/**
 * Get issue severity color for UI display.
 * 
 * @param {string} severity - Issue severity level
 * @returns {string} Tailwind CSS color class
 */
export const getIssueSeverityColor = (severity) => {
    switch (severity) {
        case 'critical':
            return 'text-red-600 bg-red-100';
        case 'error':
            return 'text-orange-600 bg-orange-100';
        case 'warning':
            return 'text-yellow-600 bg-yellow-100';
        case 'info':
        default:
            return 'text-blue-600 bg-blue-100';
    }
};

/**
 * Get issue severity icon for UI display.
 * 
 * @param {string} severity - Issue severity level
 * @returns {string} Icon character/emoji
 */
export const getIssueSeverityIcon = (severity) => {
    switch (severity) {
        case 'critical':
            return '🚨';
        case 'error':
            return '❌';
        case 'warning':
            return '⚠️';
        case 'info':
        default:
            return 'ℹ️';
    }
};
