import React, { useState, useCallback, useEffect } from 'react';
import ReactFlow, {
    ReactFlowProvider,
    addEdge,
    useNodesState,
    useEdgesState,
    Controls,
    Background,
    Handle,
    Position,
    useReactFlow
} from 'reactflow';
import 'reactflow/dist/style.css';

// --- Custom Node Components with Inline Editing ---

const NodeContainer = ({ type, label, style, children, onDelete, id }) => (
    <div className={`logic-node ${type} inline-editable`} style={style}>
        <Handle type="target" position={Position.Top} />
        <div className="node-header">
            <span className="node-type-label">{label}</span>
            {onDelete && (
                <button className="node-delete-btn" onClick={(e) => { e.stopPropagation(); onDelete(id); }}>×</button>
            )}
        </div>
        <div className="node-content">
            {children}
        </div>
        <Handle type="source" position={Position.Bottom} />
    </div>
);

const RootNode = ({ id }) => (
    <div className="logic-node root">
        <div className="node-content">
            <div className="node-title">ROOT</div>
        </div>
        <Handle type="source" position={Position.Bottom} />
    </div>
);

const SelectorNode = ({ id, data }) => {
    const { deleteNode } = useCharacterLogic();
    return (
        <NodeContainer id={id} type="selector" label="Selector (?)" onDelete={deleteNode} style={{ borderColor: '#2196F3', backgroundColor: '#E3F2FD' }}>
            <div className="node-description">Try children in order until one succeeds.</div>
        </NodeContainer>
    );
};

const SequenceNode = ({ id, data }) => {
    const { deleteNode } = useCharacterLogic();
    return (
        <NodeContainer id={id} type="sequence" label="Sequence (→)" onDelete={deleteNode} style={{ borderColor: '#4CAF50', backgroundColor: '#E8F5E9' }}>
            <div className="node-description">Run children in order until one fails.</div>
        </NodeContainer>
    );
};

const ConditionNode = ({ id, data }) => {
    const { updateNodeData, deleteNode } = useCharacterLogic();

    const handleChange = (e) => {
        updateNodeData(id, { condition: e.target.value });
    };

    return (
        <NodeContainer id={id} type="condition" label="Condition" onDelete={deleteNode} style={{ borderColor: '#FF9800', backgroundColor: '#FFF3E0' }}>
            <div className="inline-field">
                <label>Lua Condition:</label>
                <input
                    className="nodrag"
                    type="text"
                    value={data.condition || ''}
                    onChange={handleChange}
                    placeholder="e.g. player.has_item('key')"
                />
            </div>
        </NodeContainer>
    );
};

const ActionNode = ({ id, data }) => {
    const { updateNodeData, deleteNode } = useCharacterLogic();

    const handleTypeChange = (e) => {
        updateNodeData(id, { actionType: e.target.value });
    };

    const handleTextChange = (e) => {
        updateNodeData(id, { text: e.target.value });
    };

    const handleTargetChange = (e) => {
        updateNodeData(id, { targetNode: e.target.value });
    };

    return (
        <NodeContainer id={id} type="action" label="Action" onDelete={deleteNode} style={{ borderColor: '#9C27B0', backgroundColor: '#F3E5F5' }}>
            <div className="inline-field">
                <select className="nodrag" value={data.actionType || 'bark'} onChange={handleTypeChange}>
                    <option value="bark">Bark (Text)</option>
                    <option value="dialogue">Dialogue (LLM)</option>
                    <option value="move">Move To Node</option>
                    <option value="give_item">Give Item</option>
                    <option value="set_var">Set Variable</option>
                </select>
            </div>

            {(!data.actionType || data.actionType === 'bark') && (
                <div className="inline-field">
                    <textarea
                        className="nodrag"
                        rows={3}
                        value={data.text || ''}
                        onChange={handleTextChange}
                        placeholder="Text to display..."
                    />
                </div>
            )}

            {data.actionType === 'move' && (
                <div className="inline-field">
                    <input
                        className="nodrag"
                        type="text"
                        value={data.targetNode || ''}
                        onChange={handleTargetChange}
                        placeholder="Target Node ID"
                    />
                </div>
            )}
        </NodeContainer>
    );
};

const nodeTypes = {
    root: RootNode,
    selector: SelectorNode,
    sequence: SequenceNode,
    condition: ConditionNode,
    action: ActionNode,
};

// --- Context for Node Actions ---
// We use a simple context pattern via a hook to avoid prop drilling, 
// but since ReactFlow nodes are rendered independently, we need a way to pass functions.
// A common pattern is to pass them via `data`, but updating `data` triggers re-renders.
// Here we'll use a custom hook that accesses the ReactFlow instance or a provided context.

const LogicContext = React.createContext({
    updateNodeData: () => { },
    deleteNode: () => { }
});

const useCharacterLogic = () => React.useContext(LogicContext);

// --- Main Editor Component ---

const CharacterLogicEditorContent = ({ character, onUpdate }) => {
    const { fitView } = useReactFlow();
    const initialGraph = character.npc_logic?.behavior_tree || {};
    const initialNodes = Array.isArray(initialGraph.nodes) ? initialGraph.nodes : [{ id: 'root', type: 'root', position: { x: 250, y: 50 }, data: { label: 'Root' } }];
    const initialEdges = Array.isArray(initialGraph.edges) ? initialGraph.edges : [];

    const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
    const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);

    // Persist changes
    useEffect(() => {
        const timer = setTimeout(() => {
            onUpdate({
                ...character,
                npc_logic: {
                    ...character.npc_logic,
                    behavior_tree: { nodes, edges }
                }
            });
        }, 500);
        return () => clearTimeout(timer);
    }, [nodes, edges]);

    const onConnect = useCallback((params) => setEdges((eds) => addEdge(params, eds)), [setEdges]);

    const updateNodeData = useCallback((id, newData) => {
        setNodes((nds) => nds.map((node) => {
            if (node.id === id) {
                return { ...node, data: { ...node.data, ...newData } };
            }
            return node;
        }));
    }, [setNodes]);

    const deleteNode = useCallback((id) => {
        setNodes((nds) => nds.filter((n) => n.id !== id));
        setEdges((eds) => eds.filter((e) => e.source !== id && e.target !== id));
    }, [setNodes, setEdges]);

    const addNode = (type) => {
        const id = `${type}_${Date.now()}`;
        // Offset new nodes slightly to avoid stacking
        const position = {
            x: 250 + (Math.random() * 50),
            y: 200 + (Math.random() * 50)
        };

        const newNode = {
            id,
            type,
            position,
            data: { label: type }
        };
        setNodes((nds) => nds.concat(newNode));
        setTimeout(() => fitView({ duration: 500, padding: 0.2 }), 100);
    };

    return (
        <LogicContext.Provider value={{ updateNodeData, deleteNode }}>
            <div className="logic-editor-container">
                <div className="logic-toolbar">
                    <span className="toolbar-label">Add Node:</span>
                    <button onClick={() => addNode('selector')} title="Try children until one succeeds">
                        <span>?</span> Selector
                    </button>
                    <button onClick={() => addNode('sequence')} title="Run children in order">
                        <span>→</span> Sequence
                    </button>
                    <button onClick={() => addNode('condition')} title="Check a condition">
                        <span>◇</span> Condition
                    </button>
                    <button onClick={() => addNode('action')} title="Perform an action">
                        <span>⚡</span> Action
                    </button>
                </div>

                <div className="logic-canvas">
                    <ReactFlow
                        nodes={nodes}
                        edges={edges}
                        onNodesChange={onNodesChange}
                        onEdgesChange={onEdgesChange}
                        onConnect={onConnect}
                        nodeTypes={nodeTypes}
                        fitView
                        attributionPosition="bottom-right"
                    >
                        <Background />
                        <Controls />
                    </ReactFlow>
                </div>
            </div>
        </LogicContext.Provider>
    );
};

const CharacterLogicEditor = (props) => (
    <ReactFlowProvider>
        <CharacterLogicEditorContent {...props} />
    </ReactFlowProvider>
);

export default CharacterLogicEditor;
