/**
 * Graph Compiler for Character Action Graphs
 * 
 * Converts a ReactFlow graph representation into an effects array
 * that can be executed by the game engine.
 */

/**
 * Compile a graph into an effects array.
 * 
 * @param {Object} graph - The graph with nodes and edges
 * @returns {Array} - Array of effect objects
 */
export function compileGraphToEffects(graph) {
    if (!graph || !graph.nodes || graph.nodes.length === 0) {
        return [];
    }

    const { nodes, edges } = graph;
    
    // Build adjacency map: nodeId -> [connected target nodes]
    const adjacencyMap = new Map();
    edges.forEach(edge => {
        if (!adjacencyMap.has(edge.source)) {
            adjacencyMap.set(edge.source, []);
        }
        adjacencyMap.get(edge.source).push({
            target: edge.target,
            sourceHandle: edge.sourceHandle,
            targetHandle: edge.targetHandle
        });
    });
    
    // Find entry node
    const entryNode = nodes.find(n => n.type === 'entry');
    if (!entryNode) {
        console.warn('No entry node found in graph');
        return [];
    }
    
    // Build node map for quick lookup
    const nodeMap = new Map(nodes.map(n => [n.id, n]));
    
    // Track visited nodes to avoid infinite loops
    const visited = new Set();
    
    // Compile effects starting from entry node
    const effects = compileFromNode(entryNode.id, adjacencyMap, nodeMap, visited);
    
    return effects;
}

/**
 * Recursively compile effects from a node.
 */
function compileFromNode(nodeId, adjacencyMap, nodeMap, visited) {
    if (visited.has(nodeId)) {
        console.warn(`Cycle detected at node ${nodeId}`);
        return [];
    }
    
    const node = nodeMap.get(nodeId);
    if (!node) return [];
    
    visited.add(nodeId);
    const effects = [];
    
    // Convert node to effect(s)
    const nodeEffect = nodeToEffect(node);
    if (nodeEffect) {
        effects.push(nodeEffect);
    }
    
    // Handle branching for condition nodes
    if (node.type === 'condition') {
        const connections = adjacencyMap.get(nodeId) || [];
        const trueConnection = connections.find(c => c.sourceHandle === 'true');
        const falseConnection = connections.find(c => c.sourceHandle === 'false');
        
        // Compile both branches
        const trueBranchEffects = trueConnection 
            ? compileFromNode(trueConnection.target, adjacencyMap, nodeMap, new Set(visited))
            : [];
        const falseBranchEffects = falseConnection 
            ? compileFromNode(falseConnection.target, adjacencyMap, nodeMap, new Set(visited))
            : [];
        
        // Create conditional effect
        const conditionEffect = buildConditionEffect(node, trueBranchEffects, falseBranchEffects);
        if (conditionEffect) {
            // Replace or add the conditional effect
            const condIdx = effects.findIndex(e => e._nodeId === node.id);
            if (condIdx >= 0) {
                effects[condIdx] = conditionEffect;
            } else {
                effects.push(conditionEffect);
            }
        }
        
        visited.delete(nodeId);
        return effects;
    }
    
    // Handle random choice nodes
    if (node.type === 'random_choice') {
        const connections = adjacencyMap.get(nodeId) || [];
        const choices = (node.data?.choices || []).map((choice, index) => {
            const connection = connections.find(c => c.sourceHandle === `out_${index}`);
            const branchEffects = connection
                ? compileFromNode(connection.target, adjacencyMap, nodeMap, new Set(visited))
                : [];
            return {
                weight: choice.weight || 50,
                effects: branchEffects
            };
        });
        
        effects.push({
            type: 'random_choice',
            choices
        });
        
        visited.delete(nodeId);
        return effects;
    }
    
    // Follow the next connection for linear nodes
    const connections = adjacencyMap.get(nodeId) || [];
    const nextConnection = connections.find(c => c.sourceHandle === 'out' || !c.sourceHandle);
    
    if (nextConnection) {
        const nextEffects = compileFromNode(nextConnection.target, adjacencyMap, nodeMap, visited);
        effects.push(...nextEffects);
    }
    
    visited.delete(nodeId);
    return effects;
}

/**
 * Convert a single node to an effect object.
 */
function nodeToEffect(node) {
    const data = node.data || {};
    
    switch (node.type) {
        case 'entry':
        case 'exit':
            // These don't produce effects
            return null;
            
        case 'display_text':
            return {
                type: 'display_text',
                text: data.text || '',
                speaker: data.speaker || undefined
            };
            
        case 'effect':
            return buildGenericEffect(data);
            
        case 'llm_response':
            const llmEffect = {
                type: 'llm_generate',
                prompt: data.prompt || '',
                output_variable: data.output_variable || 'llm_response'
            };
            
            // If display mode is message, add a display_text after
            if (data.display_mode === 'message' || !data.display_mode) {
                return [
                    llmEffect,
                    {
                        type: 'display_text',
                        text: `{$${data.output_variable || 'llm_response'}}`
                    }
                ];
            }
            return llmEffect;
            
        case 'calculate':
            return {
                type: 'calculate',
                variable: data.variable || '',
                operation: data.operation || 'add',
                operand: parseValue(data.operand)
            };
            
        case 'script':
            return {
                type: 'script',
                script: data.script || ''
            };
            
        case 'condition':
            // Placeholder - will be replaced with full conditional in compileFromNode
            return { _nodeId: node.id, type: 'conditional' };
            
        default:
            console.warn(`Unknown node type: ${node.type}`);
            return null;
    }
}

/**
 * Build a generic effect from effect node data.
 */
function buildGenericEffect(data) {
    const effectType = data.effectType || 'set_variable';
    
    const effect = { type: effectType };
    
    switch (effectType) {
        case 'set_variable':
        case 'set_flag':
            effect.target = data.target || '';
            effect.value = parseValue(data.value);
            break;
            
        case 'add_to_inventory':
        case 'remove_from_inventory':
            effect.value = data.value || '';
            break;
            
        case 'update_object_status':
            effect.target = data.target || '';
            effect.status = data.status || '';
            break;
            
        case 'goto_node':
            effect.target = data.target || '';
            break;
            
        case 'trigger_character_action':
            effect.character_id = data.character_id || '';
            effect.action_id = data.action_id || '';
            break;
    }
    
    return effect;
}

/**
 * Build a conditional effect from a condition node.
 */
function buildConditionEffect(node, trueBranchEffects, falseBranchEffects) {
    const data = node.data || {};
    const conditionType = data.conditionType || 'variable';
    
    let condition;
    
    if (conditionType === 'lua') {
        condition = {
            type: 'script',
            script: data.script || 'return true'
        };
    } else if (conditionType === 'inventory') {
        condition = {
            type: 'inventory',
            operator: 'has',
            value: data.variable || ''
        };
    } else if (conditionType === 'flag') {
        condition = {
            type: 'state',
            variable: data.variable || '',
            operator: 'eq',
            value: true
        };
    } else {
        condition = {
            type: 'state',
            variable: data.variable || '',
            operator: data.operator || 'eq',
            value: parseValue(data.value)
        };
    }
    
    return {
        type: 'conditional',
        condition,
        if_effects: trueBranchEffects,
        else_effects: falseBranchEffects
    };
}

/**
 * Parse a value string to appropriate type.
 */
function parseValue(value) {
    if (value === undefined || value === null || value === '') {
        return value;
    }
    
    // Try to parse as number
    if (/^-?\d+(\.\d+)?$/.test(String(value))) {
        return parseFloat(value);
    }
    
    // Check for boolean
    if (value === 'true') return true;
    if (value === 'false') return false;
    
    // Return as string
    return String(value);
}

/**
 * Validate a graph structure.
 * 
 * @param {Object} graph - The graph to validate
 * @returns {Object} - { valid: boolean, errors: string[] }
 */
export function validateGraph(graph) {
    const errors = [];
    
    if (!graph || !graph.nodes) {
        errors.push('Graph is empty or invalid');
        return { valid: false, errors };
    }
    
    // Check for entry node
    const entryNodes = graph.nodes.filter(n => n.type === 'entry');
    if (entryNodes.length === 0) {
        errors.push('Graph must have an Entry node');
    } else if (entryNodes.length > 1) {
        errors.push('Graph should have only one Entry node');
    }
    
    // Check for disconnected nodes
    const connectedNodes = new Set();
    if (graph.edges) {
        graph.edges.forEach(e => {
            connectedNodes.add(e.source);
            connectedNodes.add(e.target);
        });
    }
    
    // Entry node should have outgoing connections
    if (entryNodes.length > 0 && !connectedNodes.has(entryNodes[0].id)) {
        errors.push('Entry node should be connected to other nodes');
    }
    
    return {
        valid: errors.length === 0,
        errors
    };
}

export default compileGraphToEffects;

