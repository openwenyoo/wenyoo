import React, { useState, useCallback, useEffect, useContext } from 'react';
import ReactFlow, {
    ReactFlowProvider,
    addEdge,
    useNodesState,
    useEdgesState,
    Controls,
    Background,
    Handle,
    Position,
    useReactFlow,
    MarkerType
} from 'reactflow';
import 'reactflow/dist/style.css';

// --- Port Styles ---

const PORT_COLORS = {
    exec: '#ffffff',
    string: '#ff69b4',
    number: '#4caf50',
    boolean: '#f44336',
    any: '#9e9e9e'
};

const CustomHandle = ({ type, position, dataType = 'exec', id, style = {} }) => {
    return (
        <Handle
            type={type}
            position={position}
            id={id || dataType}
            style={{
                ...style,
                background: PORT_COLORS[dataType] || PORT_COLORS.any,
                width: 10,
                height: 10,
                border: '2px solid #333',
                borderRadius: 0 // Bauhaus square handles
            }}
            title={`${dataType} ${type}`}
        />
    );
};

// --- Custom Node Components ---

const NodeContainer = ({ label, children, selected, type, onDelete, id, headerColor }) => (
    <div
        className={`effect-node ${type} ${selected ? 'selected' : ''}`}
        style={{
            minWidth: 200,
            background: 'var(--color-surface, #fff)',
            color: 'var(--color-text, #333)',
            borderRadius: 0,
            border: selected ? '2px solid var(--color-primary, blue)' : '1px solid var(--color-border, #555)',
            boxShadow: '4px 4px 0 rgba(0,0,0,0.1)'
        }}
    >
        <div className="node-header" style={{
            padding: '8px 10px',
            background: headerColor || '#333',
            color: '#fff',
            fontSize: '0.8rem',
            fontWeight: 'bold',
            textTransform: 'uppercase',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            letterSpacing: '0.05em'
        }}>
            <span>{label}</span>
            <button onClick={() => onDelete(id)} style={{ background: 'none', border: 'none', color: 'rgba(255,255,255,0.7)', cursor: 'pointer', fontSize: '1.2rem', lineHeight: 1 }}>×</button>
        </div>
        <div className="node-content" style={{ padding: 12 }}>
            {children}
        </div>
    </div>
);

// 1. Start Node
const StartNode = ({ id, selected }) => (
    <NodeContainer label="Start" type="start" selected={selected} onDelete={() => { }} id={id} headerColor="var(--color-dark, #000)">
        <div style={{ textAlign: 'right', fontSize: '0.8rem', color: '#888', paddingRight: 4, fontWeight: 'bold' }}>EXEC START</div>
        <CustomHandle type="source" position={Position.Right} dataType="exec" />
    </NodeContainer>
);

// 2. Generic Story Effect Node (Consolidated)
const EFFECT_TYPES = {
    display_text: { label: 'Display Text', color: '#2196f3' },
    set_variable: { label: 'Set Variable', color: '#9c27b0' },
    goto_node: { label: 'Goto Node', color: '#ff9800' },
    modify_inventory: { label: 'Inventory', color: '#795548' },
    llm_generate: { label: 'LLM Generate', color: '#00bcd4' }
};

const StoryEffectNode = ({ id, data, selected }) => {
    const { updateNodeData, deleteNode } = useEffectsGraph();
    const currentType = data.effectType || 'display_text';
    const config = EFFECT_TYPES[currentType] || EFFECT_TYPES.display_text;

    const handleTypeChange = (e) => {
        const newType = e.target.value;
        updateNodeData(id, { effectType: newType });
    };

    return (
        <NodeContainer
            label={config.label}
            type="story_effect"
            selected={selected}
            onDelete={deleteNode}
            id={id}
            headerColor={config.color}
        >
            <CustomHandle type="target" position={Position.Left} dataType="exec" />

            {/* Type Selector */}
            <select
                className="nodrag"
                value={currentType}
                onChange={handleTypeChange}
                style={{ width: '100%', marginBottom: 12, fontSize: '0.8rem', padding: '4px 8px', border: '1px solid #ccc', borderRadius: 0, background: '#f9f9f9' }}
            >
                {Object.entries(EFFECT_TYPES).map(([key, cfg]) => (
                    <option key={key} value={key}>{cfg.label}</option>
                ))}
            </select>

            {/* Dynamic Content */}
            {currentType === 'display_text' && (
                <textarea
                    className="nodrag"
                    value={data.text || ''}
                    onChange={(e) => updateNodeData(id, { text: e.target.value })}
                    placeholder="Message text..."
                    rows={3}
                    style={{ width: '100%', padding: 6, border: '1px solid #ccc' }}
                />
            )}

            {currentType === 'set_variable' && (
                <>
                    <input
                        className="nodrag"
                        value={data.target || ''}
                        onChange={(e) => updateNodeData(id, { target: e.target.value })}
                        placeholder="Target (e.g. score)"
                        style={{ width: '100%', marginBottom: 8, padding: 6, border: '1px solid #ccc' }}
                    />
                    <div style={{ display: 'flex', alignItems: 'center' }}>
                        <CustomHandle type="target" position={Position.Left} dataType="any" id="value_in" style={{ top: 'auto', position: 'relative', marginRight: 8 }} />
                        <input
                            className="nodrag"
                            value={data.value || ''}
                            onChange={(e) => updateNodeData(id, { value: e.target.value })}
                            placeholder="Value"
                            style={{ flex: 1, padding: 6, border: '1px solid #ccc' }}
                        />
                    </div>
                </>
            )}

            {currentType === 'goto_node' && (
                <input
                    className="nodrag"
                    value={data.target || ''}
                    onChange={(e) => updateNodeData(id, { target: e.target.value })}
                    placeholder="Target Node ID"
                    style={{ width: '100%', padding: 6, border: '1px solid #ccc' }}
                />
            )}

            {currentType === 'modify_inventory' && (
                <>
                    <select
                        className="nodrag"
                        value={data.mode || 'add'}
                        onChange={(e) => updateNodeData(id, { mode: e.target.value })}
                        style={{ width: '100%', marginBottom: 8, padding: 6, border: '1px solid #ccc' }}
                    >
                        <option value="add">Add Item</option>
                        <option value="remove">Remove Item</option>
                    </select>
                    <input
                        className="nodrag"
                        value={data.item_id || ''}
                        onChange={(e) => updateNodeData(id, { item_id: e.target.value })}
                        placeholder="Item ID"
                        style={{ width: '100%', padding: 6, border: '1px solid #ccc' }}
                    />
                </>
            )}

            {currentType === 'llm_generate' && (
                <>
                    <textarea
                        className="nodrag"
                        value={data.prompt || ''}
                        onChange={(e) => updateNodeData(id, { prompt: e.target.value })}
                        placeholder="LLM Prompt..."
                        rows={4}
                        style={{ width: '100%', marginBottom: 8, padding: 6, border: '1px solid #ccc', fontSize: '0.75rem', fontFamily: 'monospace' }}
                    />
                    <input
                        className="nodrag"
                        value={data.output_variable || ''}
                        onChange={(e) => updateNodeData(id, { output_variable: e.target.value })}
                        placeholder="Output Variable (e.g. llm_response)"
                        style={{ width: '100%', padding: 6, border: '1px solid #ccc' }}
                    />
                </>
            )}

            <CustomHandle type="source" position={Position.Right} dataType="exec" />
        </NodeContainer>
    );
};

// 3. Control Flow Nodes
const SequenceNode = ({ id, data, selected }) => {
    const { updateNodeData, deleteNode } = useEffectsGraph();
    const outputs = data.outputs || ['1', '2'];
    const addOutput = () => updateNodeData(id, { outputs: [...outputs, `${outputs.length + 1}`] });

    return (
        <NodeContainer label="Sequence" type="sequence" selected={selected} onDelete={deleteNode} id={id} headerColor="#607d8b">
            <CustomHandle type="target" position={Position.Left} dataType="exec" />
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                {outputs.map((out, idx) => (
                    <div key={idx} style={{ position: 'relative', height: 24, textAlign: 'right', display: 'flex', alignItems: 'center', justifyContent: 'flex-end' }}>
                        <span style={{ marginRight: 10, fontSize: '0.8rem', color: '#666' }}>step {idx + 1}</span>
                        <CustomHandle type="source" position={Position.Right} dataType="exec" id={`out-${idx}`} style={{ top: 'auto', position: 'relative' }} />
                    </div>
                ))}
                <button onClick={addOutput} style={{ marginTop: 4, width: '100%', fontSize: '0.75rem', padding: 4, cursor: 'pointer' }}>+ Step</button>
            </div>
        </NodeContainer>
    );
};

const ConditionNode = ({ id, data, selected }) => {
    const { updateNodeData, deleteNode } = useEffectsGraph();

    return (
        <NodeContainer label="Condition" type="condition" selected={selected} onDelete={deleteNode} id={id} headerColor="#f44336">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                <span style={{ fontSize: '0.75rem', fontWeight: 'bold' }}>INPUT</span>
                <CustomHandle type="target" position={Position.Left} dataType="exec" />
            </div>

            <div style={{ marginBottom: 12 }}>
                <input
                    className="nodrag"
                    value={data.variable || ''}
                    onChange={(e) => updateNodeData(id, { variable: e.target.value })}
                    placeholder="Variable (e.g. player.hp)"
                    style={{ width: '100%', marginBottom: 4, padding: 4, fontSize: '0.8rem', border: '1px solid #ccc' }}
                />
                <div style={{ display: 'flex', gap: 4, marginBottom: 4 }}>
                    <select
                        className="nodrag"
                        value={data.operator || 'eq'}
                        onChange={(e) => updateNodeData(id, { operator: e.target.value })}
                        style={{ flex: 1, padding: 4, fontSize: '0.8rem', border: '1px solid #ccc' }}
                    >
                        <option value="eq">==</option>
                        <option value="neq">!=</option>
                        <option value="gt">&gt;</option>
                        <option value="gte">&gt;=</option>
                        <option value="lt">&lt;</option>
                        <option value="lte">&lt;=</option>
                        <option value="exists">Exists</option>
                    </select>
                    <input
                        className="nodrag"
                        value={data.value || ''}
                        onChange={(e) => updateNodeData(id, { value: e.target.value })}
                        placeholder="Value"
                        style={{ flex: 1, padding: 4, fontSize: '0.8rem', border: '1px solid #ccc' }}
                    />
                </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <div style={{ position: 'relative', textAlign: 'right', display: 'flex', justifyContent: 'flex-end', alignItems: 'center' }}>
                    <span style={{ marginRight: 10, color: '#4caf50', fontWeight: 'bold' }}>YES</span>
                    <CustomHandle type="source" position={Position.Right} dataType="exec" id="true" />
                </div>
                <div style={{ position: 'relative', textAlign: 'right', display: 'flex', justifyContent: 'flex-end', alignItems: 'center' }}>
                    <span style={{ marginRight: 10, color: '#f44336', fontWeight: 'bold' }}>NO</span>
                    <CustomHandle type="source" position={Position.Right} dataType="exec" id="false" />
                </div>
            </div>
        </NodeContainer>
    );
};

// 4. Utility Nodes
const CalculateNode = ({ id, data, selected }) => {
    const { updateNodeData, deleteNode } = useEffectsGraph();
    return (
        <NodeContainer label="Calculate" type="calculate" selected={selected} onDelete={deleteNode} id={id} headerColor="#ff9800">
            <div style={{ marginBottom: 6, display: 'flex', alignItems: 'center' }}>
                <CustomHandle type="target" position={Position.Left} dataType="number" id="a" style={{ top: 'auto', position: 'relative', marginRight: 8 }} />
                <span>Val A</span>
            </div>
            <div style={{ marginBottom: 6, display: 'flex', alignItems: 'center' }}>
                <CustomHandle type="target" position={Position.Left} dataType="number" id="b" style={{ top: 'auto', position: 'relative', marginRight: 8 }} />
                <span>Val B</span>
            </div>
            <select
                className="nodrag"
                value={data.operation || 'add'}
                onChange={(e) => updateNodeData(id, { operation: e.target.value })}
                style={{ width: '100%', marginBottom: 10, padding: 4 }}
            >
                <option value="add">Add (+)</option>
                <option value="subtract">Subtract (-)</option>
                <option value="multiply">Multiply (*)</option>
                <option value="divide">Divide (/)</option>
            </select>
            <div style={{ textAlign: 'right', display: 'flex', justifyContent: 'flex-end', alignItems: 'center' }}>
                <span style={{ marginRight: 8, fontWeight: 'bold' }}>Result</span>
                <CustomHandle type="source" position={Position.Right} dataType="number" id="result" style={{ top: 'auto', position: 'relative' }} />
            </div>
        </NodeContainer>
    );
};

const RandomNode = ({ id, data, selected }) => {
    const { updateNodeData, deleteNode } = useEffectsGraph();
    return (
        <NodeContainer label="Random" type="random" selected={selected} onDelete={deleteNode} id={id} headerColor="#9c27b0">
            <div style={{ marginBottom: 6, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontSize: '0.8rem' }}>Min</span>
                <input
                    type="number"
                    className="nodrag"
                    value={data.min || 1}
                    onChange={(e) => updateNodeData(id, { min: parseInt(e.target.value) })}
                    style={{ width: 60, padding: 2, textAlign: 'right' }}
                />
            </div>
            <div style={{ marginBottom: 10, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontSize: '0.8rem' }}>Max</span>
                <input
                    type="number"
                    className="nodrag"
                    value={data.max || 100}
                    onChange={(e) => updateNodeData(id, { max: parseInt(e.target.value) })}
                    style={{ width: 60, padding: 2, textAlign: 'right' }}
                />
            </div>
            <div style={{ textAlign: 'right', display: 'flex', justifyContent: 'flex-end', alignItems: 'center' }}>
                <span style={{ marginRight: 8, fontWeight: 'bold' }}>Value</span>
                <CustomHandle type="source" position={Position.Right} dataType="number" id="result" />
            </div>
        </NodeContainer>
    );
};


const nodeTypes = {
    start: StartNode,
    story_effect: StoryEffectNode,
    sequence: SequenceNode,
    condition: ConditionNode,
    calculate: CalculateNode,
    random: RandomNode
};

// --- Context ---
const EffectsContext = React.createContext({ updateNodeData: () => { }, deleteNode: () => { } });
const useEffectsGraph = () => useContext(EffectsContext);

// --- Serialization ---
const serializeGraph = (nodes, edges) => {
    const executionMap = new Map();
    nodes.forEach(node => executionMap.set(node.id, node));

    // Helper to find ALL next nodes from a specific handle
    const findNextNodes = (nodeId, sourceHandleId) => {
        return edges
            .filter(e =>
                e.source === nodeId &&
                (sourceHandleId ? e.sourceHandle === sourceHandleId : (e.sourceHandle === 'exec' || e.sourceHandle === null))
            )
            .map(e => executionMap.get(e.target))
            .filter(n => n); // filter nulls
    };

    const resolveInput = (nodeId, handleId) => {
        const edge = edges.find(e => e.target === nodeId && e.targetHandle === handleId);
        if (edge) {
            const sourceNode = executionMap.get(edge.source);
            if (sourceNode && sourceNode.type === 'calculate') {
                const valA = resolveInput(sourceNode.id, 'a') || sourceNode.data.valA || 0;
                return { $type: 'calculate', op: sourceNode.data.operation, a: valA, b: resolveInput(sourceNode.id, 'b') || 0 };
            }
            if (sourceNode && sourceNode.type === 'random') {
                return { $type: 'random', min: sourceNode.data.min, max: sourceNode.data.max };
            }
            return {
                $source_node: edge.source,
                $source_output: edge.sourceHandle
            };
        }
        return null;
    };

    const traverse = (currentNodes) => {
        if (!currentNodes || currentNodes.length === 0) return [];

        // Treat 1-to-many as implicit sequence, sorted by Y
        const sortedNodes = [...currentNodes].sort((a, b) => a.position.y - b.position.y);

        const chain = [];

        for (const node of sortedNodes) {
            const visited = new Set();
            if (visited.has(node.id)) continue;

            let effect = null;
            let subChain = [];

            if (node.type === 'story_effect') {
                const effType = node.data.effectType || 'display_text';

                if (effType === 'display_text') effect = { type: 'display_text', text: node.data.text };
                else if (effType === 'set_variable') {
                    const connVal = resolveInput(node.id, 'value_in');
                    effect = { type: 'set_variable', target: node.data.target, value: connVal !== null ? connVal : node.data.value };
                }
                else if (effType === 'goto_node') effect = { type: 'goto_node', target: node.data.target };
                else if (effType === 'modify_inventory') {
                    effect = {
                        type: node.data.mode === 'remove' ? 'remove_from_inventory' : 'add_to_inventory',
                        value: node.data.item_id
                    };
                } else if (effType === 'llm_generate') {
                    effect = {
                        type: 'llm_generate',
                        prompt: node.data.prompt || '',
                        output_variable: node.data.output_variable || 'llm_response'
                    };
                } else if (effType === 'unknown') {
                    effect = node.data.raw;
                }

                // Continue traversal from this node's output
                subChain = traverse(findNextNodes(node.id, 'exec'));

            } else if (node.type === 'condition') {
                const trueNodes = findNextNodes(node.id, 'true');
                const falseNodes = findNextNodes(node.id, 'false');

                effect = {
                    type: 'conditional',
                    condition: {
                        type: 'variable',
                        variable: node.data.variable || 'temp',
                        operator: node.data.operator || 'eq',
                        value: node.data.value
                    },
                    if_effects: traverse(trueNodes),
                    else_effects: traverse(falseNodes)
                };
            } else if (node.type === 'sequence') {
                const outputs = node.data.outputs || ['1', '2'];
                const seq = [];
                outputs.forEach((_, idx) => seq.push(...traverse(findNextNodes(node.id, `out-${idx}`))));
                chain.push(...seq);
                effect = null;
            }

            if (effect) chain.push(effect);
            if (subChain.length > 0) chain.push(...subChain);
        }

        return chain;
    };

    const startNode = nodes.find(n => n.type === 'start');
    if (!startNode) return [];
    return traverse(findNextNodes(startNode.id, 'exec'));
};

const deserializeEffects = (effects) => {
    let nodes = [{ id: 'start', type: 'start', position: { x: 50, y: 150 }, data: {} }];
    let edges = [];

    if (!effects || effects.length === 0) return { nodes, edges };

    const processChain = (chain, prevId, x, y, srcHandle = 'exec') => {
        let curPrev = prevId;
        let curX = x;
        let curY = y;
        let curSrcHandle = srcHandle;

        if (!chain) return;

        chain.forEach((eff, idx) => {
            const id = `node_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`;
            let type = 'story_effect';
            let data = { effectType: 'display_text' };

            if (eff.type === 'display_text') data = { effectType: 'display_text', text: eff.text };
            else if (eff.type === 'set_variable') data = { effectType: 'set_variable', target: eff.target, value: eff.value };
            else if (eff.type === 'goto_node') data = { effectType: 'goto_node', target: eff.target };
            else if (eff.type === 'add_to_inventory' || eff.type === 'remove_from_inventory') {
                data = {
                    effectType: 'modify_inventory',
                    mode: eff.type === 'remove_from_inventory' ? 'remove' : 'add',
                    item_id: eff.value || eff.item_id
                };
            } else if (eff.type === 'llm_generate') {
                data = {
                    effectType: 'llm_generate',
                    prompt: eff.prompt || '',
                    output_variable: eff.output_variable || 'llm_response'
                };
            } else if (eff.type === 'conditional') {
                type = 'condition';
                data = {
                    variable: eff.condition?.variable,
                    operator: eff.condition?.operator,
                    value: eff.condition?.value
                };
            } else {
                data = { effectType: 'unknown', raw: eff };
            }

            // Vertical spacing for implicit sequence list items?
            // Or horizontal? User's mental model is probably linear flow horizontally, with branches.
            // But if we serialized multiple outputs as a sequence, deserializing them back to a line is safer.
            // Let's assume standard horizontal flow for now unless branching.

            nodes.push({ id, type, position: { x: curX, y: curY }, data });

            if (curPrev) {
                edges.push({ id: `e_${curPrev}_${id}`, source: curPrev, target: id, sourceHandle: curSrcHandle, targetHandle: 'exec', type: 'default', markerEnd: { type: MarkerType.ArrowClosed } });
            }

            if (type === 'condition') {
                if (eff.if_effects) processChain(eff.if_effects, id, curX + 250, curY - 100, 'true');
                if (eff.else_effects) processChain(eff.else_effects, id, curX + 250, curY + 100, 'false');
                curPrev = null;
            } else {
                curPrev = id;
                curX += 250;
                // curSrcHandle = 'exec';
            }
        });
    };

    processChain(effects, 'start', 300, 150);
    return { nodes, edges };
};

// --- Main ---

const EffectsGraphEditorContent = ({ initialEffects = [], onChange }) => {
    const { fitView } = useReactFlow();
    const [nodes, setNodes, onNodesChange] = useNodesState([]);
    const [edges, setEdges, onEdgesChange] = useEdgesState([]);
    const lastSerializedRef = React.useRef(null);

    // Initial load & External updates
    useEffect(() => {
        const incomingJson = JSON.stringify(initialEffects);

        // If the incoming data matches what we just serialized, it's an "echo" update.
        // We SHOULD NOT re-deserialize because that would destroy the user's current layout.
        if (lastSerializedRef.current === incomingJson) {
            return;
        }

        // Otherwise, it's new data (loading a different action, or external undo/redo).
        // We must re-deserialize and layout.
        const { nodes: n, edges: e } = deserializeEffects(initialEffects);
        setNodes(n);
        setEdges(e);

        // Update reference so we don't think this fresh state is a user change
        // Wait, if we set lastSerializedRef here, the NEXT serialize effect might not fire?
        // Actually, we want the serialize effect to compare against THIS.
        // But if we set it here, we handle the case perfectly.
        lastSerializedRef.current = incomingJson;

        setTimeout(() => fitView({ duration: 500 }), 100);
    }, [initialEffects]); // Dependency on initialEffects is correct

    const updateNodeData = useCallback((id, data) => {
        setNodes(nds => nds.map(n => n.id === id ? { ...n, data: { ...n.data, ...data } } : n));
    }, [setNodes]);

    const deleteNode = useCallback((id) => {
        setNodes(nds => nds.filter(n => n.id !== id));
        setEdges(eds => eds.filter(e => e.source !== id && e.target !== id));
    }, [setNodes, setEdges]);

    const onConnect = useCallback((params) => setEdges((eds) => addEdge({ ...params, type: 'default', markerEnd: { type: MarkerType.ArrowClosed } }, eds)), [setEdges]);

    const addNode = (type, subData = {}) => {
        const id = `${type}_${Date.now()}`;
        setNodes(nds => nds.concat({
            id, type, position: { x: 250 + Math.random() * 50, y: 150 + Math.random() * 50 }, data: subData
        }));
    };

    // Serialization & Change Notification
    useEffect(() => {
        const timeoutId = setTimeout(() => {
            if (nodes.length > 0) {
                const serialized = serializeGraph(nodes, edges);
                const jsonSerialized = JSON.stringify(serialized);

                // Only trigger onChange if the data is LOGICALLY different from the last known state.
                // This prevents:
                // 1. Initial mount firing onChange (if initial matches serialized)
                // 2. Layout-only changes firing onChange (since serialization ignores layout)
                // 3. Infinite loops
                if (onChange && jsonSerialized !== lastSerializedRef.current) {
                    lastSerializedRef.current = jsonSerialized;
                    onChange(serialized);
                }
            }
        }, 1000); // Debounce
        return () => clearTimeout(timeoutId);
    }, [nodes, edges, onChange]); // lastSerializedRef is ref

    return (
        <EffectsContext.Provider value={{ updateNodeData, deleteNode }}>
            <div className="effects-graph-editor" style={{ width: '100%', height: '500px', display: 'flex', flexDirection: 'column' }}>
                <div className="effects-toolbar">
                    <div className="toolbar-group">
                        <span className="toolbar-label">Add Node:</span>
                        <button className="toolbar-btn toolbar-btn-effect" onClick={() => addNode('story_effect', { effectType: 'display_text' })}>
                            <span className="btn-icon">⚡</span> Effect
                        </button>
                        <button className="toolbar-btn toolbar-btn-flow" onClick={() => addNode('condition')}>
                            <span className="btn-icon">◇</span> Condition
                        </button>
                        <button className="toolbar-btn toolbar-btn-util" onClick={() => addNode('calculate')}>
                            <span className="btn-icon">∑</span> Calc
                        </button>
                        <button className="toolbar-btn toolbar-btn-util" onClick={() => addNode('random', { min: 1, max: 100 })}>
                            <span className="btn-icon">🎲</span> Random
                        </button>
                    </div>
                </div>
                <div style={{ flex: 1, background: 'var(--color-bg, #f0f0f0)' }}>
                    <ReactFlow
                        nodes={nodes}
                        edges={edges}
                        onNodesChange={onNodesChange}
                        onEdgesChange={onEdgesChange}
                        onConnect={onConnect}
                        nodeTypes={nodeTypes}
                        fitView
                    >
                        <Background color="#ccc" gap={20} />
                        <Controls />
                    </ReactFlow>
                </div>
            </div >
        </EffectsContext.Provider >
    );
};

const EffectsGraphEditor = (props) => (
    <ReactFlowProvider>
        <EffectsGraphEditorContent {...props} />
    </ReactFlowProvider>
);

export default EffectsGraphEditor;
