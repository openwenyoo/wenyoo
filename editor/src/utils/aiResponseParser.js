/**
 * AI Response Parser - Parses and validates LLM responses
 */

/**
 * Parse the AI response and validate structure
 * @param {string} responseText - Raw response from LLM
 * @returns {Object} {success: boolean, data?: Object, error?: string}
 */
export function parseAIResponse(responseText) {
    try {
        // Remove markdown code blocks if present
        let cleanedText = responseText.trim();
        if (cleanedText.startsWith('```')) {
            cleanedText = cleanedText.replace(/^```(?:json)?\n?/, '').replace(/\n?```$/, '');
        }

        const parsed = JSON.parse(cleanedText);

        // Check if multi-operation format
        if (parsed.operations && Array.isArray(parsed.operations)) {
            // Validate each operation
            for (let i = 0; i < parsed.operations.length; i++) {
                const op = parsed.operations[i];
                const validation = validateSingleOperation(op, i);
                if (!validation.success) {
                    return validation;
                }
            }

            return {
                success: true,
                data: {
                    isMultiOp: true,
                    operations: parsed.operations
                }
            };
        } else {
            // Single operation format
            const validation = validateSingleOperation(parsed);
            if (!validation.success) {
                return validation;
            }

            return {
                success: true,
                data: {
                    isMultiOp: false,
                    operation: parsed.operation,
                    nodes: parsed.nodes || [],
                    edges: parsed.edges || [],
                    explanation: parsed.explanation || 'No explanation provided'
                }
            };
        }
    } catch (error) {
        return {
            success: false,
            error: `Failed to parse AI response: ${error.message}`
        };
    }
}

/**
 * Validate a single operation
 * @param {Object} op - Operation to validate
 * @param {number} index - Index in multi-op array (optional)
 * @returns {Object} Validation result
 */
function validateSingleOperation(op, index) {
    const opLabel = index !== undefined ? `Operation ${index + 1}` : 'Operation';

    // Check required fields
    if (!op.operation) {
        return { success: false, error: `${opLabel}: Missing 'operation' field` };
    }

    if (!op.nodes || !Array.isArray(op.nodes)) {
        return { success: false, error: `${opLabel}: Missing or invalid 'nodes' array` };
    }

    if (!op.edges || !Array.isArray(op.edges)) {
        return { success: false, error: `${opLabel}: Missing or invalid 'edges' array` };
    }

    // Normalize operation type (handle singular/plural mismatch)
    let operationType = op.operation;
    const opMap = {
        'create_node': 'create_nodes',
        'update_node': 'update_nodes',
        'replace_node': 'replace_nodes'
    };

    if (opMap[operationType]) {
        operationType = opMap[operationType];
        op.operation = operationType; // Update the object for downstream use
    }

    // Validate operation type
    const validOps = ['create_nodes', 'update_nodes', 'replace_nodes'];
    if (!validOps.includes(op.operation)) {
        return {
            success: false,
            error: `${opLabel}: Invalid operation '${op.operation}'. Must be one of: ${validOps.join(', ')}`
        };
    }

    // Validate nodes structure
    const nodeValidation = validateNodes(op.nodes, opLabel);
    if (!nodeValidation.success) {
        return nodeValidation;
    }

    return { success: true };
}

/**
 * Validate nodes array
 * @param {Array} nodes - Nodes to validate
 * @param {string} opLabel - Operation label for error messages
 * @returns {Object} Validation result
 */
function validateNodes(nodes, opLabel = 'Operation') {
    if (nodes.length === 0) {
        console.warn(`${opLabel}: Empty nodes array`);
    }

    for (let i = 0; i < nodes.length; i++) {
        const node = nodes[i];

        // Check required fields
        if (!node.id) {
            return { success: false, error: `${opLabel}: Node ${i} missing 'id' field` };
        }

        // Normalize actions before validation
        if (node.actions) {
            node.actions = normalizeActions(node.actions);
            const actionValidation = validateActions(node.actions, node.id, opLabel);
            if (!actionValidation.success) {
                return actionValidation;
            }
        }

        // Normalize object actions too
        if (node.objects) {
            for (const obj of node.objects) {
                if (obj.actions) {
                    obj.actions = normalizeActions(obj.actions);
                }
            }
        }
    }

    return { success: true };
}

/**
 * Normalize actions to handle LLM field naming inconsistencies
 * @param {Array} actions - Actions to normalize
 * @returns {Array} Normalized actions
 */
function normalizeActions(actions) {
    return actions.map(action => {
        const normalized = { ...action };

        // Convert 'label' or 'description' to 'text'
        if (!normalized.text) {
            if (normalized.label) {
                normalized.text = normalized.label;
                delete normalized.label;
            } else if (normalized.description && !normalized.text) {
                normalized.text = normalized.description;
            }
        }

        return normalized;
    });
}

/**
 * Validate actions array
 * @param {Array} actions - Actions to validate
 * @param {string} nodeId - Node ID for error messages
 * @param {string} opLabel - Operation label for error messages
 * @returns {Object} Validation result
 */
function validateActions(actions, nodeId, opLabel = 'Operation') {
    for (let i = 0; i < actions.length; i++) {
        const action = actions[i];

        // Check required fields
        if (!action.id) {
            return { success: false, error: `${opLabel}: Node '${nodeId}' action ${i} missing 'id'` };
        }

        if (!action.text) {
            return { success: false, error: `${opLabel}: Node '${nodeId}' action '${action.id}' missing 'text' field (not 'name')` };
        }

        // Check for common mistakes
        if (action.effects) {
            for (const effect of action.effects) {
                if (effect.type === 'goto_node' && !effect.target) {
                    return {
                        success: false,
                        error: `${opLabel}: Node '${nodeId}' action '${action.id}' missing 'target' field in goto_node effect`
                    };
                }
            }
        }
    }

    return { success: true };
}
