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
    useReactFlow,
    MarkerType
} from 'reactflow';
import 'reactflow/dist/style.css';

// --- Custom Node Components ---

const NodeContainer = ({ type, label, style, children, onDelete, id }) => (
    <div className={`logic-node ${type} inline-editable`} style={{ ...style, minWidth: '150px' }}>
        <Handle type="target" position={Position.Left} />
        <div className="node-header">
            <span className="node-type-label">{label}</span>
            {onDelete && (
                <button className="node-delete-btn" onClick={(e) => { e.stopPropagation(); onDelete(id); }}>×</button>
            )}
        </div>
        <div className="node-content">
            {children}
        </div>
        <Handle type="source" position={Position.Right} />
    </div>
);

const StateNode = ({ id, data }) => {
    const { updateNodeData, deleteNode } = useFSMEditor();

    const handleNameChange = (e) => {
        updateNodeData(id, { label: e.target.value });
    };

    const handleDescriptionChange = (e) => {
        updateNodeData(id, { description: e.target.value });
    };

    return (
        <NodeContainer
            id={id}
            type="state"
            label="State"
            onDelete={deleteNode}
            style={{ borderColor: '#673AB7', backgroundColor: '#EDE7F6' }}
        >
            <div className="inline-field">
                <input
                    className="nodrag"
                    type="text"
                    value={data.label || ''}
                    onChange={handleNameChange}
                    placeholder="State Name"
                    style={{ fontWeight: 'bold' }}
                />
            </div>
            <div className="inline-field">
                <textarea
                    className="nodrag"
                    rows={2}
                    value={data.description || ''}
                    onChange={handleDescriptionChange}
                    placeholder="Description..."
                />
            </div>
        </NodeContainer>
    );
};

const nodeTypes = {
    state: StateNode,
};

// --- Context ---

const FSMContext = React.createContext({
    updateNodeData: () => { },
    deleteNode: () => { }
});

const useFSMEditor = () => React.useContext(FSMContext);

// --- Main Editor Content ---

const CharacterFSMEditorContent = ({ character, onUpdate }) => {
    const { fitView } = useReactFlow();
    // Load initial graph from character.npc_logic.fsm or default
    const initialGraph = character.npc_logic?.fsm || {};
    const initialNodes = Array.isArray(initialGraph.nodes) ? initialGraph.nodes : [
        { id: 'state_1', type: 'state', position: { x: 100, y: 100 }, data: { label: 'Idle', description: 'Default state' } }
    ];
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
                    fsm: { nodes, edges }
                }
            });
        }, 500);
        return () => clearTimeout(timer);
    }, [nodes, edges]);

    const onConnect = useCallback((params) => {
        setEdges((eds) => addEdge({
            ...params,
            type: 'default',
            markerEnd: { type: MarkerType.ArrowClosed }
        }, eds));
    }, [setEdges]);

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

    const addState = () => {
        const id = `state_${Date.now()}`;
        const position = {
            x: 100 + (Math.random() * 50),
            y: 100 + (Math.random() * 50)
        };

        const newNode = {
            id,
            type: 'state',
            position,
            data: { label: 'New State', description: '' }
        };
        setNodes((nds) => nds.concat(newNode));
        setTimeout(() => fitView({ duration: 500, padding: 0.2 }), 100);
    };

    return (
        <FSMContext.Provider value={{ updateNodeData, deleteNode }}>
            <div className="logic-editor-container" style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
                <div className="logic-toolbar">
                    <button onClick={addState}>Add State</button>
                    <span style={{ marginLeft: 'auto', fontSize: '0.8rem', color: '#666' }}>
                        Connect states to define transitions
                    </span>
                </div>

                <div className="logic-canvas" style={{ flex: 1, minHeight: 0 }}>
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
        </FSMContext.Provider>
    );
};

const CharacterFSMEditor = (props) => (
    <ReactFlowProvider>
        <CharacterFSMEditorContent {...props} />
    </ReactFlowProvider>
);

export default CharacterFSMEditor;
