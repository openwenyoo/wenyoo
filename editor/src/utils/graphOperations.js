/**
 * Graph Operations - Apply AI-generated changes to the graph
 */

/**
 * Apply AI changes to the graph based on operation type
 * @param {string} operation - Type of operation
 * @param {Array} newNodes - Nodes from AI
 * @param {Array} newEdges - Edges from AI
 * @param {Object} currentGraph - Current graph state
 * @returns {Object} {nodes, edges} - Updated graph
 */
export function applyAIChanges(operation, newNodes, newEdges, currentGraph) {
    const { nodes, edges } = currentGraph;

    switch (operation) {
        case 'create_nodes':
            return createNewNodes(newNodes, newEdges, nodes, edges);
        case 'update_nodes':
            return updateExistingNodes(newNodes, nodes, edges);
        case 'replace_nodes':
            return replaceNodes(newNodes, newEdges, nodes, edges);
        default:
            throw new Error(`Unknown operation: ${operation}`);
    }
}

/**
 * Create new nodes and add them to the graph
 * @param {Array} newNodes - New nodes to add
 * @param {Array} newEdges - New edges to add
 * @param {Array} existingNodes - Current nodes
 * @param {Array} existingEdges - Current edges
 * @returns {Object} {nodes, edges}
 */
function createNewNodes(newNodes, newEdges, existingNodes, existingEdges) {
    // Convert new nodes to React Flow format
    const reactFlowNodes = newNodes.map((nodeData, index) => ({
        id: nodeData.id,
        type: 'detailed',
        data: {
            ...nodeData,
            label: nodeData.id,
            viewMode: 'default' // Will be set by current view mode
        },
        position: {
            x: 100 + (index * 300),
            y: 100 + (index * 150)
        }
    }));

    return {
        nodes: [...existingNodes, ...reactFlowNodes],
        edges: existingEdges
    };
}

/**
 * Update existing nodes with new data
 * @param {Array} updatedNodes - Nodes with updates
 * @param {Array} existingNodes - Current nodes
 * @param {Array} existingEdges - Current edges
 * @returns {Object} {nodes, edges}
 */
function updateExistingNodes(updatedNodes, existingNodes, existingEdges) {
    const updateMap = new Map(updatedNodes.map(n => [n.id, n]));

    const nodes = existingNodes.map(node => {
        const update = updateMap.get(node.id);
        if (update) {
            // If updating a pseudo/generated node, convert it to detailed
            const isConversion = node.type === 'pseudo' || node.type === 'generated';
            const hasContent = update.name && (update.explicit_state || update.definition);
            const newType = (isConversion && hasContent) ? 'detailed' : node.type;

            return {
                ...node,
                type: newType,
                data: {
                    ...node.data,
                    // Merge update with existing data
                    id: update.id,
                    name: update.name !== undefined ? update.name : node.data.name,
                    // DSPP fields
                    definition: update.definition !== undefined ? update.definition : node.data.definition,
                    explicit_state: update.explicit_state !== undefined ? update.explicit_state : node.data.explicit_state,
                    implicit_state: update.implicit_state !== undefined ? update.implicit_state : node.data.implicit_state,
                    properties: update.properties !== undefined ? update.properties : node.data.properties,
                    // Merge arrays instead of replacing - ignore empty arrays from LLM
                    actions: mergeArraysById(node.data.actions, update.actions),
                    objects: mergeArraysById(node.data.objects, update.objects),
                    triggers: mergeArraysById(node.data.triggers, update.triggers),
                    is_ending: update.is_ending !== undefined ? update.is_ending : node.data.is_ending,
                    label: update.name || update.id,
                    viewMode: node.data.viewMode || 'full' // Ensure viewMode is set
                }
            };
        }
        return node;
    });

    return {
        nodes,
        edges: existingEdges
    };
}

/**
 * Merge two arrays by ID - new items are appended, existing items are updated
 * If newArray is empty or undefined, returns existing array unchanged
 * @param {Array} existing - Existing array
 * @param {Array} incoming - New array from LLM
 * @returns {Array} Merged array
 */
function mergeArraysById(existing, incoming) {
    // If no incoming data or empty array, preserve existing
    if (!incoming || (Array.isArray(incoming) && incoming.length === 0)) {
        return existing || [];
    }

    // If no existing data, use incoming
    if (!existing || existing.length === 0) {
        return incoming;
    }

    // Merge: update existing items by id, append new ones
    const existingMap = new Map((existing || []).map(item => [item.id, item]));
    const result = [...existing];

    for (const incomingItem of incoming) {
        const existingIndex = result.findIndex(e => e.id === incomingItem.id);
        if (existingIndex >= 0) {
            // Update existing item
            result[existingIndex] = { ...result[existingIndex], ...incomingItem };
        } else {
            // Append new item
            result.push(incomingItem);
        }
    }

    return result;
}

/**
 * Replace selected nodes with new nodes
 * @param {Array} replacementNodes - New nodes to replace with
 * @param {Array} replacementEdges - New edges
 * @param {Array} existingNodes - Current nodes
 * @param {Array} existingEdges - Current edges
 * @returns {Object} {nodes, edges}
 */
function replaceNodes(replacementNodes, replacementEdges, existingNodes, existingEdges) {
    // Get IDs of selected nodes
    const selectedIds = existingNodes.filter(n => n.selected).map(n => n.id);

    if (selectedIds.length === 0) {
        throw new Error('No nodes selected for replacement');
    }

    // Get position of first selected node for placement
    const firstSelected = existingNodes.find(n => n.selected);
    const startX = firstSelected?.position.x || 100;
    const startY = firstSelected?.position.y || 100;

    // Remove selected nodes
    const remainingNodes = existingNodes.filter(n => !selectedIds.includes(n.id));

    // Remove edges connected to selected nodes
    const remainingEdges = existingEdges.filter(e =>
        !selectedIds.includes(e.source) && !selectedIds.includes(e.target)
    );

    // Convert replacement nodes to React Flow format
    const reactFlowNodes = replacementNodes.map((nodeData, index) => ({
        id: nodeData.id,
        type: 'detailed',
        data: {
            ...nodeData,
            label: nodeData.id,
            viewMode: 'default'
        },
        position: {
            x: startX + (index * 50),
            y: startY + (index * 150)
        }
    }));

    return {
        nodes: [...remainingNodes, ...reactFlowNodes],
        edges: remainingEdges
    };
}
