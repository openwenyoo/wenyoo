import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import ReactFlow, {
    ReactFlowProvider,
    addEdge,
    useNodesState,
    useEdgesState,
    Controls,
    applyNodeChanges,
} from 'reactflow';
import 'reactflow/dist/style.css';
import axios from 'axios';
import './App.css';
import './styles/menu-toolbar.css';
import './styles/ai-assistant.css';
import './styles/plan-review.css';
import './styles/character-panel.css';
import './styles/nodes.css';
import './editor-panels.css';
import './styles/node-editor-specifics.css';
import NodeEditor from './components/NodeEditor';
import ContextMenu from './components/ContextMenu';
import SecondaryEditor from './components/SecondaryEditor';
import CharacterPanel from './components/CharacterPanel';
import ParameterPanel from './components/ParameterPanel';
import LorePanel from './components/LorePanel';
import ObjectPanel from './components/ObjectPanel';
import FloatingToolPanel from './components/FloatingToolPanel';
import MenuBar from './components/MenuBar';
import DetailedNode from './components/DetailedNode';
import PseudoNode from './components/PseudoNode';
import GenerateNode from './components/GenerateNode';
import GroupNode from './components/GroupNode';
import VersionHistoryDialog from './components/VersionHistoryDialog';
import ConfirmDialog from './components/ConfirmDialog';
import InputDialog from './components/InputDialog';
import LoadingPanel from './components/LoadingPanel';
import ImportWizard from './components/ImportWizard';
import { getLayoutedElements, CustomEdge, generateEdgesFromConnections } from './utils/graphLayout.jsx';
import { useGraphHistory } from './hooks/useGraphHistory';
import { useLocale } from './i18n';
import { 
    handleLlmSubmit, 
    handleBatchConvert, 
    streamAIEdit, 
    AI_SOURCES, 
    EDIT_MODES, 
    calculateNewNodePosition,
    generatePlan,
    executePlan,
    quickGenerate,
    generateOutlines,
    expandOutline,
    refineOutline,
    refineOutlines,
    refineDetailedOutline,
    conductStory,
    reviewStory
} from './services/aiService';
import PlanReviewPanel from './components/PlanReviewPanel';
import OutlineSelector from './components/OutlineSelector';
import {
    loadStory,
    saveStory,
    compileConnectionGraph,
    createNewStory,
    backupOriginal,
    getVersions,
    restoreVersion,
    buildGeneratedStoryPayload,
    createStoryFromGenerated,
    generateStoryId
} from './services/storyService';

// --- Main App Component ---
const AppContent = () => {
    const { t } = useLocale();
    const [nodes, setNodes, onNodesChange] = useNodesState([]);
    const [edges, setEdges, onEdgesChange] = useEdgesState([]);
    const [storyId, setStoryId] = useState(null);
    const [stories, setStories] = useState([]);
    const [showLoadingPanel, setShowLoadingPanel] = useState(true);
    const [selectedNode, setSelectedNode] = useState(null);
    const [storyData, setStoryData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [llmPrompt, setLlmPrompt] = useState('');
    const [llmLoading, setLlmLoading] = useState(false);
    const [aiThinkingMessage, setAiThinkingMessage] = useState('');
    const [useStreamingAI, setUseStreamingAI] = useState(true); // Toggle between streaming and legacy mode
    const [usePlanBasedAI, setUsePlanBasedAI] = useState(true); // Use plan-based approach
    const [currentPlan, setCurrentPlan] = useState(null);
    const [showPlanReview, setShowPlanReview] = useState(false);
    const [planExecuting, setPlanExecuting] = useState(false);
    const [planCurrentStep, setPlanCurrentStep] = useState(null);
    const [planProgress, setPlanProgress] = useState(0);
    const [showOutlineSelector, setShowOutlineSelector] = useState(false);
    const [showImportWizard, setShowImportWizard] = useState(false);
    const [activeImportDraft, setActiveImportDraft] = useState(null);
    // Wizard initial state (set by AI panel before opening wizard)
    const [wizardInitialIdea, setWizardInitialIdea] = useState('');
    const [wizardInitialPhase, setWizardInitialPhase] = useState(null); // null, 'selecting', 'detailed'
    const [wizardInitialOutlines, setWizardInitialOutlines] = useState([]);
    const [wizardInitialDetailedOutline, setWizardInitialDetailedOutline] = useState(null);
    const [wizardInitialPlan, setWizardInitialPlan] = useState(null);
    const [loadedFrom, setLoadedFrom] = useState('original');
    const [tempPath, setTempPath] = useState(null);
    const [contextMenu, setContextMenu] = useState(null);
    const [copiedNode, setCopiedNode] = useState(null);
    const reactFlowWrapper = useRef(null);
    const [selectedShape, setSelectedShape] = useState(null);
    const [secondaryEditorOpen, setSecondaryEditorOpen] = useState(false);
    const [reactFlowInstance, setReactFlowInstance] = useState(null);
    const [isAiPanelOpen, setIsAiPanelOpen] = useState(false);
    const [viewMode, setViewMode] = useState('detailed');
    const viewModeRef = useRef(viewMode);
    const [showCharacterPanel, setShowCharacterPanel] = useState(false);
    const [editingCharacterId, setEditingCharacterId] = useState(null);
    const [showParameterPanel, setShowParameterPanel] = useState(false);
    const [showLorePanel, setShowLorePanel] = useState(false);
    const [showObjectPanel, setShowObjectPanel] = useState(false);
    const [showVersionHistory, setShowVersionHistory] = useState(false);
    const [confirmDialog, setConfirmDialog] = useState({ isOpen: false, action: null, data: null });
    const [inputDialog, setInputDialog] = useState({ isOpen: false, callback: null });
    const [hoveredNodeId, setHoveredNodeId] = useState(null);
    const [selectedConnectionId, setSelectedConnectionId] = useState(null);
    const [graphStatus, setGraphStatus] = useState({ status: 'missing', currentConnectionGraphSourceMd5: null, connectionGraphSourceMd5: null });
    const [graphCompileLoading, setGraphCompileLoading] = useState(false);
    const selectedNodeCount = nodes.filter((node) => node.selected).length;

    const refreshStories = useCallback(async () => {
        try {
            const response = await axios.get('/api/stories');
            setStories(response.data);
        } catch (error) {
            console.error('Failed to load story list:', error);
        }
    }, []);

    useEffect(() => {
        viewModeRef.current = viewMode;
    }, [viewMode]);

    // Use history hook
    const {
        addToHistory,
        addToHistoryRef,
        handleUndo,
        handleRedo,
        canUndo,
        canRedo,
        setHistoryIndex,
        markAsSaved,
        resetSavedIndex,
        unsavedCount,
        clearHistory
    } = useGraphHistory();

    // Register custom node types
    const nodeTypes = useMemo(() => ({
        default: NodeEditor,
        detailed: DetailedNode,
        pseudo: PseudoNode,
        generated: GenerateNode,
        group: GroupNode
    }), []);

    const edgeTypes = useMemo(() => ({
        custom: CustomEdge
    }), []);

    // Add highlighted prop to edges connected to hovered node
    const edgesWithHighlight = useMemo(() => {
        if (!hoveredNodeId) return edges;
        return edges.map(edge => ({
            ...edge,
            data: {
                ...edge.data,
                highlighted: edge.source === hoveredNodeId || edge.target === hoveredNodeId
            }
        }));
    }, [edges, hoveredNodeId]);

    const syncConnectionEdges = useCallback((nextStoryData, nextNodes) => {
        const nextEdges = generateEdgesFromConnections(nextStoryData, nextNodes);
        setEdges(nextEdges);
        return nextEdges;
    }, [setEdges]);

    const updateStoryConnections = useCallback((updater, nextNodes = nodes, { trackHistory = true } = {}) => {
        let nextStoryDataSnapshot = storyData;

        setStoryData((prev) => {
            const base = prev || {};
            const nextStoryData = updater(base);
            nextStoryDataSnapshot = nextStoryData;
            return nextStoryData;
        });

        const nextEdges = syncConnectionEdges(nextStoryDataSnapshot, nextNodes);
        if (trackHistory) {
            addToHistory(nextNodes, nextEdges);
        }
        return { storyData: nextStoryDataSnapshot, edges: nextEdges };
    }, [addToHistory, nodes, storyData, syncConnectionEdges]);

    const selectedConnection = useMemo(() => {
        return (storyData?.connections || []).find((connection) => connection.id === selectedConnectionId) || null;
    }, [storyData, selectedConnectionId]);

    useEffect(() => {
        if (selectedConnectionId && !selectedConnection) {
            setSelectedConnectionId(null);
        }
    }, [selectedConnection, selectedConnectionId]);

    // Initial history push - REMOVED (clearHistory handles initialization)
    // The previous useEffect caused duplicate history entries on load
    /*
    useEffect(() => {
        if (nodes.length > 0 && addToHistoryRef.current) {
            // Only add first time
            if (canUndo === false && nodes.length > 0) {
                addToHistory(nodes, edges);
            }
        }
    }, [nodes, edges, addToHistory, addToHistoryRef, canUndo]);
    */

    // Handle undo
    const performUndo = () => {
        const prevState = handleUndo();
        if (prevState) {
            setNodes(prevState.nodes);
            setEdges(prevState.edges);
            setHistoryIndex(prev => prev - 1);
        }
    };

    // Handle redo
    const performRedo = () => {
        const nextState = handleRedo();
        if (nextState) {
            setNodes(nextState.nodes);
            setEdges(nextState.edges);
            setHistoryIndex(prev => prev + 1);
        }
    };

    // Wrap onNodesChange to track history (specifically for deletions/hotkeys)
    const onNodesChangeWithHistory = useCallback((changes) => {
        // Detect significant changes like deletion
        const hasReduction = changes.some(c => c.type === 'remove');

        if (hasReduction) {
            // Apply changes immediately to get new state
            const nextNodes = applyNodeChanges(changes, nodes);
            const removedNodeIds = new Set(
                changes
                    .filter((change) => change.type === 'remove')
                    .map((change) => change.id)
            );

            setNodes(nextNodes);
            updateStoryConnections((prev) => ({
                ...prev,
                connections: (prev.connections || []).filter((connection) => {
                    if (removedNodeIds.has(connection.source)) {
                        return false;
                    }
                    return !(connection.targets || []).some((target) => removedNodeIds.has(target));
                }),
            }), nextNodes);
        } else {
            // Standard update for drag/select
            setNodes((nds) => applyNodeChanges(changes, nds));
        }
    }, [nodes, updateStoryConnections]);

    // Custom node change handler for direct updates
    const updateNodesAndHistory = (newNodes) => {
        const newEdges = generateEdgesFromConnections(storyData, newNodes);

        setNodes(newNodes);
        setEdges(newEdges);
        addToHistory(newNodes, newEdges);
    };

    // Handle click from DetailedNode items
    const handleShapeClickFromNode = useCallback((item, type) => {
        setNodes(currentNodes => {
            const parentNode = currentNodes.find(n => {
                if (type === 'object') return n.data.objects?.some(o => o.id === item.id);
                if (type === 'action') return n.data.actions?.some(a => a.id === item.id);
                if (type === 'trigger') return n.data.triggers?.some(t => t.id === item.id);
                return false;
            });

            if (parentNode) {
                setSelectedNode(parentNode);
                setSelectedShape({ type, shape: item });
                setSecondaryEditorOpen(true);
            }
            return currentNodes;
        });
    }, [setNodes]);

    // Load story wrapper
    const loadStoryWrapper = useCallback(async (id, temp_path = null) => {
        setLoading(true);
        try {
            const result = await loadStory(id, temp_path, viewModeRef.current, handleShapeClickFromNode);
            setStoryData(result.storyData);
            setNodes(result.nodes);
            setEdges(result.edges);
            setGraphStatus(result.graphStatus);
            setLoadedFrom(result.loadedFrom);
            setTempPath(result.tempPath);

            // Backup original when loading (creates version 0 if it doesn't exist)
            await backupOriginal(id);

            // Use clearHistory to reset history and saved state
            clearHistory(result.nodes, result.edges);
        } catch (error) {
            console.error("Error loading story:", error);
        } finally {
            setLoading(false);
        }
    }, [handleShapeClickFromNode, setNodes, setEdges, clearHistory]);

    // Load story list on mount
    useEffect(() => {
        refreshStories();
    }, [refreshStories]);

    // Load story when storyId changes (and is not null)
    // Skip loading if the story was just created locally (loadedFrom === 'new')
    const skipLoadRef = useRef(false);
    
    useEffect(() => {
        if (storyId) {
            setShowLoadingPanel(false);
            // Skip loading if we just created a new story
            if (skipLoadRef.current) {
                skipLoadRef.current = false;
                return;
            }
            loadStoryWrapper(storyId);
        }
    }, [storyId, loadStoryWrapper]);

    // Handle View Mode Change
    const handleViewModeChange = (mode) => {
        setViewMode(mode);

        const updatedNodes = nodes.map(node => ({
            ...node,
            type: 'detailed',
            data: {
                ...node.data,
                viewMode: mode
            }
        }));

        const layouted = getLayoutedElements(updatedNodes, edges, 'LR', mode);
        setNodes(layouted.nodes);
        setEdges(layouted.edges);
    };

    // Save story wrapper
    const saveStoryWrapper = async () => {
        try {
            await saveStory(storyId, nodes, storyData);
            await loadStoryWrapper(storyId);
            markAsSaved();
            alert(t('app.storySaved'));
        } catch (error) {
            console.error("Error saving story:", error);
            alert(t('app.storySaveFailed'));
        }
    };

    // Prevent accidental close with unsaved changes
    useEffect(() => {
        const handleBeforeUnload = (e) => {
            if (unsavedCount > 0) {
                e.preventDefault();
                e.returnValue = '';
            }
        };

        window.addEventListener('beforeunload', handleBeforeUnload);
        return () => {
            window.removeEventListener('beforeunload', handleBeforeUnload);
        };
    }, [unsavedCount]);

    // Handle actions that require confirmation
    const handleActionWithCheck = (actionType, data = null) => {
        if (unsavedCount > 0) {
            setConfirmDialog({
                isOpen: true,
                action: actionType,
                data: data
            });
        } else {
            performAction(actionType, data);
        }
    };

    const performAction = (actionType, data) => {
        if (actionType === 'new') {
            // Show input dialog for story title
            setInputDialog({
                isOpen: true,
                callback: (title) => {
                    const result = createNewStory(title, viewMode, handleShapeClickFromNode);
                    setStoryData(result.storyData);
                    setNodes(result.nodes);
                    setEdges(result.edges);
                    skipLoadRef.current = true; // Skip loading for newly created story
                    setStoryId(result.storyId);
                    clearHistory(result.nodes, result.edges);
                    setLoadedFrom('new');
                    setLoading(false); // Mark loading as complete
                }
            });
        } else if (actionType === 'load') {
            setStoryId(data);
        }
    };

    const handleInputDialogConfirm = (value) => {
        if (inputDialog.callback) {
            inputDialog.callback(value);
        }
        setInputDialog({ isOpen: false, callback: null });
    };

    const handleInputDialogCancel = () => {
        setInputDialog({ isOpen: false, callback: null });
    };

    const handleConfirmSave = async () => {
        await saveStoryWrapper();
        setConfirmDialog({ isOpen: false, action: null, data: null });
        performAction(confirmDialog.action, confirmDialog.data);
    };

    const handleConfirmDontSave = () => {
        setConfirmDialog({ isOpen: false, action: null, data: null });
        performAction(confirmDialog.action, confirmDialog.data);
    };

    const handleConfirmCancel = () => {
        setConfirmDialog({ isOpen: false, action: null, data: null });
    };

    // New story handler
    const handleNewStory = () => {
        handleActionWithCheck('new');
    };

    // Load story handler
    const handleLoadStory = (id) => {
        handleActionWithCheck('load', id);
    };

    // Loading panel handlers
    const handleLoadingPanelCreate = (title) => {
        const result = createNewStory(title, viewMode, handleShapeClickFromNode);
        setStoryData(result.storyData);
        setNodes(result.nodes);
        setEdges(result.edges);
        skipLoadRef.current = true; // Skip loading for newly created story
        setStoryId(result.storyId);
        clearHistory(result.nodes, result.edges);
        setLoadedFrom('new');
        setLoading(false); // Mark loading as complete
        setShowLoadingPanel(false);
    };

    const handleLoadingPanelLoad = (id) => {
        setStoryId(id);
        // setShowLoadingPanel(false) is handled in the useEffect
    };

    const handleLoadingPanelImport = () => {
        setShowImportWizard(true);
    };

    const handleImportConversionReady = ({ importDraft, writerIntent, detailedOutline, plan }) => {
        setActiveImportDraft(importDraft);
        setWizardInitialIdea(writerIntent);
        setWizardInitialPhase('detailed');
        setWizardInitialOutlines([]);
        setWizardInitialDetailedOutline(detailedOutline || null);
        setWizardInitialPlan(plan || null);
        setShowImportWizard(false);
        setShowOutlineSelector(true);
    };

    // Restore version handler
    const handleRestoreVersion = async (version) => {
        const result = await restoreVersion(storyId, version);
        if (result.success) {
            await loadStoryWrapper(storyId);
            alert(t('app.restoreSuccess', { version, backupVersion: result.backed_up_as }));
        } else {
            alert(t('app.restoreFailed', { error: result.error }));
        }
    };

    const buildManualConnectionId = useCallback((source, target) => {
        return `${source}_to_${target}`;
    }, []);

    // Event handlers
    const onConnect = useCallback((params) => {
        if (!params?.source || !params?.target) {
            return;
        }

        const newConnection = {
            id: buildManualConnectionId(params.source, params.target),
            source: params.source,
            targets: [params.target],
        };

        updateStoryConnections((prev) => ({
            ...prev,
            connections: [...(prev.connections || []), newConnection],
        }));

        setSelectedNode(null);
        setSelectedConnectionId(newConnection.id);
    }, [buildManualConnectionId, updateStoryConnections]);

    const handleEdgeClick = useCallback((event, edge) => {
        event?.preventDefault?.();
        setSelectedNode(null);
        setSecondaryEditorOpen(false);
        setSelectedShape(null);
        setSelectedConnectionId(edge?.data?.connectionId || null);
    }, []);

    const handleEdgesDelete = useCallback((deletedEdges) => {
        const deletedConnectionIds = new Set(
            (deletedEdges || [])
                .map((edge) => edge?.data?.connectionId)
                .filter(Boolean)
        );

        if (deletedConnectionIds.size === 0) {
            return;
        }

        updateStoryConnections((prev) => ({
            ...prev,
            connections: (prev.connections || []).filter(
                (connection) => !deletedConnectionIds.has(connection.id)
            ),
        }));
    }, [updateStoryConnections]);

    const onNodeDoubleClick = useCallback((event, node) => {
        setSelectedNode(node);
        setSecondaryEditorOpen(false);
        setSelectedShape(null);
    }, []);

    const handlePaneClick = useCallback(() => {
        setSelectedNode(null);
        setSelectedConnectionId(null);
        setSecondaryEditorOpen(false);
        setSelectedShape(null);
        setContextMenu(null);
        setShowCharacterPanel(false);
        setEditingCharacterId(null);
        setShowParameterPanel(false);
        setShowLorePanel(false);
        setShowObjectPanel(false);
    }, []);

    // Handler to open character panel for a specific character
    const handleEditCharacter = useCallback((charId) => {
        setEditingCharacterId(charId);
        setShowCharacterPanel(true);
        setSelectedNode(null);
        setShowParameterPanel(false);
        setShowLorePanel(false);
        setShowObjectPanel(false);
    }, []);

    const handleNodeContextMenu = useCallback((event, node) => {
        event.preventDefault();
        setContextMenu({
            x: event.clientX,
            y: event.clientY,
            nodeId: node.id,
        });
    }, []);

    const handlePaneContextMenu = useCallback((event) => {
        event.preventDefault();
        setContextMenu({
            x: event.clientX,
            y: event.clientY,
            nodeId: null,
        });
    }, []);

    const handleAddNode = useCallback((x, y) => {
        const id = `node_${Date.now()}`;
        const position = reactFlowInstance ? reactFlowInstance.screenToFlowPosition({ x, y }) : { x, y };

        const newNode = {
            id,
            type: viewMode === 'detailed' ? 'detailed' : 'default',
            position,
            data: {
                id,
                label: id,
                name: 'New Node',
                definition: '',
                explicit_state: '',
                implicit_state: '',
                properties: {},
                objects: [],
                actions: [],
                triggers: [],
                viewMode: viewMode,
                onShapeClick: handleShapeClickFromNode
            },
        };
        setNodes((nds) => nds.concat(newNode));
        addToHistory([...nodes, newNode], edges);
        setContextMenu(null);
    }, [nodes, edges, viewMode, handleShapeClickFromNode, reactFlowInstance, addToHistory, setNodes]);

    const handleAddPseudoNode = useCallback((x, y) => {
        const id = `pseudo_${Date.now()}`;
        const position = reactFlowInstance ? reactFlowInstance.screenToFlowPosition({ x, y }) : { x, y };

        const newNode = {
            id,
            type: 'pseudo',
            position,
            data: {
                id,
                prompt: '',
                onChange: (newPrompt) => {
                    setNodes((nds) => nds.map((node) => {
                        if (node.id === id) {
                            return { ...node, data: { ...node.data, prompt: newPrompt } };
                        }
                        return node;
                    }));
                }
            },
        };
        setNodes((nds) => nds.concat(newNode));
        addToHistory([...nodes, newNode], edges);
        setContextMenu(null);
    }, [nodes, edges, reactFlowInstance, setNodes, addToHistory]);

    const handleAddGenerateNode = useCallback((x, y) => {
        const id = `gen_${Date.now()}`;
        const position = reactFlowInstance ? reactFlowInstance.screenToFlowPosition({ x, y }) : { x, y };

        const newNode = {
            id,
            type: 'generated',
            position,
            data: {
                id,
                generation_prompt: '',
                onChange: (newPrompt) => {
                    setNodes((nds) => nds.map((node) => {
                        if (node.id === id) {
                            return { ...node, data: { ...node.data, generation_prompt: newPrompt } };
                        }
                        return node;
                    }));
                }
            },
        };
        setNodes((nds) => nds.concat(newNode));
        addToHistory([...nodes, newNode], edges);
        setContextMenu(null);
    }, [nodes, edges, reactFlowInstance, setNodes, addToHistory]);

    // Grouping Logic
    const handleGroupNodes = useCallback(() => {
        const selectedNodes = nodes.filter(n => n.selected && !n.parentNode && n.type !== 'group');
        if (selectedNodes.length < 2) return;

        // Calculate bounding box
        const xMin = Math.min(...selectedNodes.map(n => n.position.x));
        const yMin = Math.min(...selectedNodes.map(n => n.position.y));
        const xMax = Math.max(...selectedNodes.map(n => n.position.x + (n.width || 250))); // default width
        const yMax = Math.max(...selectedNodes.map(n => n.position.y + (n.height || 100))); // default height

        const padding = 40;
        const groupPosition = {
            x: xMin - padding,
            y: yMin - padding
        };
        const groupWidth = xMax - xMin + padding * 2;
        const groupHeight = yMax - yMin + padding * 2;

        const groupId = `group_${Date.now()}`;
        const groupNode = {
            id: groupId,
            type: 'group',
            position: groupPosition,
            style: { width: groupWidth, height: groupHeight, zIndex: -1 },
            data: {
                label: 'Group',
                onChange: (newLabel) => {
                    setNodes(nds => nds.map(n => n.id === groupId ? { ...n, data: { ...n.data, label: newLabel } } : n));
                }
            },
        };

        const newNodes = nodes.map(node => {
            if (node.selected && !node.parentNode && node.type !== 'group') {
                return {
                    ...node,
                    parentNode: groupId,
                    extent: 'parent',
                    position: {
                        x: node.position.x - groupPosition.x,
                        y: node.position.y - groupPosition.y
                    }
                };
            }
            return node;
        }).concat(groupNode);

        setNodes(newNodes);
        addToHistory(newNodes, edges);
        setContextMenu(null);
    }, [nodes, edges, setNodes, addToHistory]);

    const handleUngroupNodes = useCallback(() => {
        const selectedGroup = nodes.find(n => n.selected && n.type === 'group');
        if (!selectedGroup) return;

        const groupPosition = selectedGroup.position;

        // Find children
        const childNodes = nodes.filter(n => n.parentNode === selectedGroup.id);

        const newNodes = nodes.filter(n => n.id !== selectedGroup.id).map(node => {
            if (node.parentNode === selectedGroup.id) {
                return {
                    ...node,
                    parentNode: undefined,
                    extent: undefined,
                    position: {
                        x: node.position.x + groupPosition.x,
                        y: node.position.y + groupPosition.y
                    }
                };
            }
            return node;
        });

        setNodes(newNodes);
        addToHistory(newNodes, edges);
        setContextMenu(null);
    }, [nodes, edges, setNodes, addToHistory]);

    // Batch convert handler
    const handleBatchConvertWrapper = async () => {
        setLlmLoading(true);
        try {
            await handleBatchConvert({
                nodes,
                edges,
                storyData,
                viewMode,
                handleShapeClickFromNode,
                onSuccess: (newNodes, newEdges) => {
                    setNodes(newNodes);
                    setEdges(newEdges);
                    addToHistory(newNodes, newEdges);
                },
                onError: (message) => {
                    alert(message);
                }
            });
        } finally {
            setLlmLoading(false);
        }
    };

    const handleCopyNode = () => {
        if (contextMenu) {
            const nodeToCopy = nodes.find(n => n.id === contextMenu.nodeId);
            if (nodeToCopy) {
                setCopiedNode(nodeToCopy);
                setContextMenu(null);
            }
        }
    };

    const handleUpdateCharacters = (newCharacters) => {
        setStoryData(prev => ({
            ...prev,
            characters: newCharacters
        }));

        setNodes(nds => nds.map(node => {
            const nodeCharacters = newCharacters.filter(c =>
                c.properties?.location === node.id
            );
            return {
                ...node,
                data: { ...node.data, characters: nodeCharacters }
            };
        }));
    };

    const handlePasteNode = () => {
        if (copiedNode && contextMenu) {
            const newNodeId = `${copiedNode.id}_copy_${Date.now()}`;
            const newNode = {
                ...copiedNode,
                id: newNodeId,
                position: { x: contextMenu.x, y: contextMenu.y },
                data: { ...copiedNode.data, id: newNodeId, label: newNodeId, onShapeClick: handleShapeClickFromNode }
            };
            const newNodes = [...nodes, newNode];
            setNodes(newNodes);
            addToHistory(newNodes, edges);
            setContextMenu(null);
        }
    };

    const handleDeleteNode = () => {
        if (contextMenu) {
            const newNodes = nodes.filter(n => n.id !== contextMenu.nodeId);
            setNodes(newNodes);
            updateStoryConnections((prev) => ({
                ...prev,
                connections: (prev.connections || []).filter((connection) => {
                    if (connection.source === contextMenu.nodeId) {
                        return false;
                    }
                    return !(connection.targets || []).includes(contextMenu.nodeId);
                }),
            }), newNodes);
            setContextMenu(null);
            if (selectedNode && selectedNode.id === contextMenu.nodeId) {
                setSelectedNode(null);
            }
        }
    };

    const handleNodeChange = (updatedNode) => {
        let fullUpdatedNode = null;
        const newNodes = nodes.map(n => {
            if (n.id === updatedNode.id) {
                fullUpdatedNode = {
                    ...n,
                    data: { ...updatedNode, label: updatedNode.id, onShapeClick: handleShapeClickFromNode }
                };
                return fullUpdatedNode;
            }
            return n;
        });
        updateNodesAndHistory(newNodes);
        if (fullUpdatedNode) {
            setSelectedNode(fullUpdatedNode);
        }
    };

    const handleConnectionIdChange = useCallback((value) => {
        if (!selectedConnectionId) {
            return;
        }

        const trimmedValue = value.trim();
        if (!trimmedValue) {
            return;
        }

        updateStoryConnections((prev) => ({
            ...prev,
            connections: (prev.connections || []).map((connection) =>
                connection.id === selectedConnectionId
                    ? { ...connection, id: trimmedValue }
                    : connection
            ),
        }), nodes, { trackHistory: false });
        setSelectedConnectionId(trimmedValue);
    }, [nodes, selectedConnectionId, updateStoryConnections]);

    const handleDeleteSelectedConnection = useCallback(() => {
        if (!selectedConnectionId) {
            return;
        }

        updateStoryConnections((prev) => ({
            ...prev,
            connections: (prev.connections || []).filter(
                (connection) => connection.id !== selectedConnectionId
            ),
        }));
        setSelectedConnectionId(null);
    }, [selectedConnectionId, updateStoryConnections]);

    const handleCompileGraph = useCallback(async () => {
        if (!storyId) {
            return;
        }

        setGraphCompileLoading(true);
        try {
            await compileConnectionGraph(storyId, { tempPath });
            await loadStoryWrapper(storyId, tempPath);
        } catch (error) {
            console.error('Error compiling connection graph:', error);
            alert(t('app.compileGraphFailed'));
        } finally {
            setGraphCompileLoading(false);
        }
    }, [loadStoryWrapper, storyId, t, tempPath]);

    // Update edge styles
    useEffect(() => {
        setEdges((eds) =>
            eds.map((edge) => ({ ...edge, animated: true, style: {} }))
        );
    }, [selectedNode, setEdges]);

    const handleShapeClick = (shape, type) => {
        setSelectedShape({ type, shape });
        setSecondaryEditorOpen(true);
    };

    const handleUpdateShape = (updatedShape) => {
        if (!selectedNode || !selectedShape) return;

        // Clone the current data
        const updatedNodeData = { ...selectedNode.data };
        let shapeArray;
        let shapeIndex;

        switch (selectedShape.type) {
            case 'object':
                shapeArray = [...(updatedNodeData.objects || [])];
                shapeIndex = shapeArray.findIndex(s => s.id === updatedShape.id);
                if (shapeIndex !== -1) {
                    shapeArray[shapeIndex] = updatedShape;
                } else {
                    shapeArray.push(updatedShape);
                }
                updatedNodeData.objects = shapeArray;
                break;
            case 'action':
                shapeArray = [...(updatedNodeData.actions || [])];
                shapeIndex = shapeArray.findIndex(s => s.id === updatedShape.id);
                if (shapeIndex !== -1) {
                    shapeArray[shapeIndex] = updatedShape;
                } else {
                    shapeArray.push(updatedShape);
                }
                updatedNodeData.actions = shapeArray;
                break;
            case 'trigger':
                shapeArray = [...(updatedNodeData.triggers || [])];
                shapeIndex = shapeArray.findIndex(s => s.id === updatedShape.id);
                if (shapeIndex !== -1) {
                    shapeArray[shapeIndex] = updatedShape;
                } else {
                    shapeArray.push(updatedShape);
                }
                updatedNodeData.triggers = shapeArray;
                break;
            default:
                return;
        }

        const newNodes = nodes.map(n => (n.id === selectedNode.id ? { ...n, data: { ...updatedNodeData, onShapeClick: handleShapeClickFromNode } } : n));
        updateNodesAndHistory(newNodes);

        // Update selectedNode so local state remains consistent
        setSelectedNode({ ...selectedNode, data: updatedNodeData });
    };

    // AI Assistant Logic - Streaming Mode (New Function Calling Approach)
    const handleStreamingAISubmit = async () => {
        setLlmLoading(true);
        setAiThinkingMessage(t('app.aiStatus.starting'));
        
        await streamAIEdit({
            prompt: llmPrompt,
            mode: EDIT_MODES.STORY_CREATION,  // Use story_creation mode for full story editing
            nodes,
            edges,
            characters: storyData?.characters || [],
            objects: storyData?.objects || [],
            parameters: storyData?.initial_variables || {},
            storyData,
            source: AI_SOURCES.MAIN_GRAPH,
            viewMode,
            
            onThinking: (message) => {
                setAiThinkingMessage(message);
            },
            
            onFunctionCall: (functionName, args) => {
                setAiThinkingMessage(t('app.aiStatus.callingFunction', { functionName }));
            },
            
            onNodeCreated: (rfNode, rfEdges) => {
                // Add node with animation class
                const position = rfNode.position || calculateNewNodePosition(nodes);
                const newNode = {
                    ...rfNode,
                    position,
                    className: 'ai-created-animation',
                    data: {
                        ...rfNode.data,
                        onShapeClick: handleShapeClickFromNode
                    }
                };
                setNodes(prev => [...prev, newNode]);
                
                // Add edges
                if (rfEdges && rfEdges.length > 0) {
                    setEdges(prev => [...prev, ...rfEdges]);
                }
                
                setAiThinkingMessage(t('app.aiStatus.createdNode', { name: rfNode.data?.name || rfNode.id }));
            },
            
            onNodeUpdated: (nodeData, updatedFields, newEdges) => {
                setNodes(prev => prev.map(n => {
                    if (n.id === nodeData.id) {
                        return {
                            ...n,
                            className: 'ai-updated-animation',
                            data: {
                                ...n.data,
                                ...nodeData,
                                onShapeClick: handleShapeClickFromNode
                            }
                        };
                    }
                    return n;
                }));
                
                // Add any new edges
                if (newEdges && newEdges.length > 0) {
                    setEdges(prev => [...prev, ...newEdges]);
                }
                
                setAiThinkingMessage(t('app.aiStatus.updatedNode', { name: nodeData.name || nodeData.id }));
            },
            
            onNodeDeleted: (nodeId) => {
                // Add deletion animation class, then remove after delay
                setNodes(prev => prev.map(n => 
                    n.id === nodeId ? { ...n, className: 'ai-deleted-animation' } : n
                ));
                setTimeout(() => {
                    setNodes(prev => prev.filter(n => n.id !== nodeId));
                    setEdges(prev => prev.filter(e => e.source !== nodeId && e.target !== nodeId));
                }, 300);
                
                setAiThinkingMessage(t('app.aiStatus.deletedNode', { name: nodeId }));
            },
            
            onEdgeCreated: (rfEdge) => {
                console.debug('Ignoring AI-created visual edge; editor graph is derived from story.connections only.', rfEdge);
            },
            
            onEdgeDeleted: (edgeId) => {
                console.debug('Ignoring AI edge deletion event; editor graph is derived from story.connections only.', edgeId);
            },
            
            // Character events (for story_creation mode)
            onCharacterCreated: (character) => {
                setStoryData(prev => ({
                    ...prev,
                    characters: [...(prev?.characters || []), character]
                }));
                setAiThinkingMessage(t('app.aiStatus.createdCharacter', { name: character.name || character.id }));
            },
            
            onCharacterUpdated: (character, updatedFields) => {
                setStoryData(prev => ({
                    ...prev,
                    characters: (prev?.characters || []).map(c =>
                        c.id === character.id ? { ...c, ...character } : c
                    )
                }));
                setAiThinkingMessage(t('app.aiStatus.updatedCharacter', { name: character.name || character.id }));
            },
            
            onCharacterDeleted: (characterId) => {
                setStoryData(prev => ({
                    ...prev,
                    characters: (prev?.characters || []).filter(c => c.id !== characterId)
                }));
                setAiThinkingMessage(t('app.aiStatus.deletedCharacter', { name: characterId }));
            },
            
            // Object events (for story_creation mode)
            onObjectCreated: (obj) => {
                setStoryData(prev => ({
                    ...prev,
                    objects: [...(prev?.objects || []), obj]
                }));
                setAiThinkingMessage(t('app.aiStatus.createdObject', { name: obj.name || obj.id }));
            },
            
            onObjectUpdated: (obj, updatedFields) => {
                setStoryData(prev => ({
                    ...prev,
                    objects: (prev?.objects || []).map(o =>
                        o.id === obj.id ? { ...o, ...obj } : o
                    )
                }));
                setAiThinkingMessage(t('app.aiStatus.updatedObject', { name: obj.name || obj.id }));
            },
            
            onObjectDeleted: (objectId) => {
                setStoryData(prev => ({
                    ...prev,
                    objects: (prev?.objects || []).filter(o => o.id !== objectId)
                }));
                setAiThinkingMessage(t('app.aiStatus.deletedObject', { name: objectId }));
            },
            
            // Parameter events (for story_creation mode)
            onParameterSet: (key, value, isNew) => {
                setStoryData(prev => ({
                    ...prev,
                    initial_variables: { ...(prev?.initial_variables || {}), [key]: value }
                }));
                setAiThinkingMessage(
                    isNew
                        ? t('app.aiStatus.createdParameter', { key })
                        : t('app.aiStatus.updatedParameter', { key })
                );
            },
            
            onParameterDeleted: (key) => {
                setStoryData(prev => {
                    const newVars = { ...(prev?.initial_variables || {}) };
                    delete newVars[key];
                    return { ...prev, initial_variables: newVars };
                });
                setAiThinkingMessage(t('app.aiStatus.deletedParameter', { key }));
            },
            
            onComplete: ({ message, summary }) => {
                setLlmLoading(false);
                setAiThinkingMessage('');
                addToHistory(nodes, edges);
                setLlmPrompt('');
                setIsAiPanelOpen(false);
                
                // Build comprehensive summary
                let summaryParts = [];
                if (summary) {
                    if (summary.nodes_created || summary.nodes_updated || summary.nodes_deleted) {
                        summaryParts.push(t('app.summary.nodes', {
                            created: summary.nodes_created || 0,
                            updated: summary.nodes_updated || 0,
                            deleted: summary.nodes_deleted || 0,
                        }));
                    }
                    if (summary.characters_created || summary.characters_updated || summary.characters_deleted) {
                        summaryParts.push(t('app.summary.characters', {
                            created: summary.characters_created || 0,
                            updated: summary.characters_updated || 0,
                        }));
                    }
                    if (summary.objects_created || summary.objects_updated || summary.objects_deleted) {
                        summaryParts.push(t('app.summary.objects', {
                            created: summary.objects_created || 0,
                            updated: summary.objects_updated || 0,
                        }));
                    }
                    if (summary.parameters_set || summary.parameters_deleted) {
                        summaryParts.push(t('app.summary.parameters', {
                            count: summary.parameters_set || 0,
                        }));
                    }
                }
                const summaryText = summaryParts.join('\n');
                alert(t('app.aiComplete', { summary: summaryText, message }));
            },
            
            onError: (error) => {
                setLlmLoading(false);
                setAiThinkingMessage('');
                alert(t('app.aiError', { error }));
            }
        });
    };

    // AI Assistant Logic - Legacy Mode (JSON Response + Engine Handle)
    const handleLegacyAISubmit = async () => {
        setLlmLoading(true);
        try {
            await handleLlmSubmit({
                llmPrompt,
                nodes,
                edges,
                storyData,
                onSuccess: (newNodes, newEdges, message) => {
                    setNodes(newNodes);
                    setEdges(newEdges);
                    addToHistory(newNodes, newEdges);
                    alert(message);
                    setLlmPrompt('');
                    setIsAiPanelOpen(false);
                },
                onError: (message) => {
                    alert(`Error: ${message}`);
                }
            });
        } finally {
            setLlmLoading(false);
        }
    };

    // AI Assistant Logic - Plan-Based Mode (Two-phase: Generate Plan, then Execute)
    const handlePlanBasedAISubmit = async () => {
        setLlmLoading(true);
        setAiThinkingMessage(t('app.aiStatus.analyzing'));
        
        try {
            // Get selected node IDs
            const selectedNodeIds = nodes.filter(n => n.selected).map(n => n.id);
            
            // Check if this is a new story request (empty or near-empty graph)
            const isNewStory = nodes.length <= 1;
            
            if (isNewStory) {
                // For new stories, route through the wizard
                const wordCount = llmPrompt.trim().split(/\s+/).length;
                const isDetailedInput = wordCount > 50; // Detailed if more than 50 words
                
                if (isDetailedInput) {
                    // Detailed input - expand directly to Step 3
                    setAiThinkingMessage(t('app.aiStatus.creatingPlan'));
                    try {
                        const result = await expandOutline({ 
                            summary: llmPrompt,
                            title: t('outline.customTitle'),
                            theme: llmPrompt.substring(0, 100)
                        });
                        
                        if (result) {
                            // Set wizard initial state and open at Step 3 (detailed/review)
                            setWizardInitialIdea(llmPrompt);
                            setWizardInitialPhase('detailed');
                            setWizardInitialOutlines([]);
                            setWizardInitialDetailedOutline(result.detailedOutline || result);
                            setWizardInitialPlan(result.plan || null);
                            setIsAiPanelOpen(false);
                            setShowOutlineSelector(true);
                            setLlmPrompt('');
                        }
                    } catch (err) {
                        console.error('Failed to expand outline:', err);
                        // Fallback to Step 2
                        setAiThinkingMessage(t('app.aiStatus.generatingDirections'));
                        const outlines = await generateOutlines(llmPrompt);
                        if (outlines && outlines.length > 0) {
                            setWizardInitialIdea(llmPrompt);
                            setWizardInitialPhase('selecting');
                            setWizardInitialOutlines(outlines);
                            setWizardInitialDetailedOutline(null);
                            setWizardInitialPlan(null);
                            setIsAiPanelOpen(false);
                            setShowOutlineSelector(true);
                            setLlmPrompt('');
                        }
                    }
                } else {
                    // Short/vague input - generate outlines for Step 2
                    setAiThinkingMessage(t('app.aiStatus.generatingDirections'));
                    const outlines = await generateOutlines(llmPrompt);
                    
                    if (outlines && outlines.length > 0) {
                        // Set wizard initial state and open at Step 2 (selecting)
                        setWizardInitialIdea(llmPrompt);
                        setWizardInitialPhase('selecting');
                        setWizardInitialOutlines(outlines);
                        setWizardInitialDetailedOutline(null);
                        setWizardInitialPlan(null);
                        setIsAiPanelOpen(false);
                        setShowOutlineSelector(true);
                        setLlmPrompt('');
                    } else {
                        throw new Error(t('outline.failedDirections', { error: t('generic.error') }));
                    }
                }
                
                setLlmLoading(false);
                setAiThinkingMessage('');
                return;
            }
            
            // For existing stories, use normal plan-based editing
            // Generate plan
            const plan = await generatePlan({
                prompt: llmPrompt,
                nodes,
                edges,
                characters: storyData?.characters || [],
                objects: storyData?.objects || [],
                parameters: storyData?.initial_variables || {},
                selectedNodeIds,
                storyMetadata: {
                    title: storyData?.name || storyData?.title,
                    genre: storyData?.genre
                }
            });
            
            setCurrentPlan(plan);
            setLlmLoading(false);
            setAiThinkingMessage('');
            setShowPlanReview(true);
            
        } catch (error) {
            setLlmLoading(false);
            setAiThinkingMessage('');
            alert(t('app.aiError', { error: error.message }));
        }
    };
    
    // Execute the reviewed plan
    const handleExecutePlan = async (plan) => {
        setPlanExecuting(true);
        setPlanProgress(0);
        
        const totalSteps = plan.steps.length;
        let completedSteps = 0;
        
        await executePlan({
            plan,
            nodes,
            edges,
            characters: storyData?.characters || [],
            objects: storyData?.objects || [],
            parameters: storyData?.initial_variables || {},
            viewMode,
            
            onThinking: (message, data) => {
                setAiThinkingMessage(message);
                if (data?.current_step) {
                    setPlanCurrentStep(data.current_step);
                    completedSteps = data.current_step;
                    setPlanProgress(Math.round((completedSteps / totalSteps) * 100));
                }
            },
            
            onNodeCreated: (rfNode, rfEdges) => {
                const position = rfNode.position || calculateNewNodePosition(nodes);
                const newNode = {
                    ...rfNode,
                    position,
                    className: 'ai-created-animation',
                    data: { ...rfNode.data, onShapeClick: handleShapeClickFromNode }
                };
                setNodes(prev => [...prev, newNode]);
                if (rfEdges && rfEdges.length > 0) {
                    setEdges(prev => [...prev, ...rfEdges]);
                }
            },
            
            onNodeUpdated: (nodeData, updatedFields, newEdges) => {
                setNodes(prev => prev.map(n => {
                    if (n.id === nodeData.id) {
                        return {
                            ...n,
                            className: 'ai-updated-animation',
                            data: { ...n.data, ...nodeData, onShapeClick: handleShapeClickFromNode }
                        };
                    }
                    return n;
                }));
                if (newEdges && newEdges.length > 0) {
                    setEdges(prev => [...prev, ...newEdges]);
                }
            },
            
            onNodeDeleted: (nodeId) => {
                setNodes(prev => prev.map(n =>
                    n.id === nodeId ? { ...n, className: 'ai-deleted-animation' } : n
                ));
                setTimeout(() => {
                    setNodes(prev => prev.filter(n => n.id !== nodeId));
                    setEdges(prev => prev.filter(e => e.source !== nodeId && e.target !== nodeId));
                }, 300);
            },
            
            onEdgeCreated: (rfEdge) => {
                console.debug('Ignoring AI-created visual edge; editor graph is derived from story.connections only.', rfEdge);
            },
            
            onEdgeDeleted: (edgeId) => {
                console.debug('Ignoring AI edge deletion event; editor graph is derived from story.connections only.', edgeId);
            },
            
            onCharacterCreated: (character) => {
                setStoryData(prev => ({
                    ...prev,
                    characters: [...(prev?.characters || []), character]
                }));
            },
            
            onCharacterUpdated: (character) => {
                setStoryData(prev => ({
                    ...prev,
                    characters: (prev?.characters || []).map(c =>
                        c.id === character.id ? { ...c, ...character } : c
                    )
                }));
            },
            
            onParameterSet: (key, value) => {
                setStoryData(prev => ({
                    ...prev,
                    initial_variables: { ...(prev?.initial_variables || {}), [key]: value }
                }));
            },
            
            onComplete: ({ message, summary }) => {
                setPlanExecuting(false);
                setShowPlanReview(false);
                setCurrentPlan(null);
                setAiThinkingMessage('');
                setPlanCurrentStep(null);
                setPlanProgress(0);
                addToHistory(nodes, edges);
                setLlmPrompt('');
                setIsAiPanelOpen(false);
                
                let summaryParts = [];
                if (summary) {
                    if (summary.nodes_created) summaryParts.push(t('app.planSummary.nodes', { count: summary.nodes_created }));
                    if (summary.characters_created) summaryParts.push(t('app.planSummary.characters', { count: summary.characters_created }));
                    if (summary.parameters_set) summaryParts.push(t('app.planSummary.parameters', { count: summary.parameters_set }));
                }
                alert(t('app.planExecuted', { summary: summaryParts.join(', '), message }));
            },
            
            onError: (error) => {
                setPlanExecuting(false);
                setAiThinkingMessage('');
                alert(t('app.executionError', { error }));
            }
        });
    };

    const handleWizardGenerateOutlines = useCallback((idea, numOptions = 3) => (
        generateOutlines(idea, numOptions)
    ), []);

    const handleWizardExpandOutline = useCallback((outline, modifications = null) => (
        expandOutline(outline, modifications)
    ), []);
    
    // Handle outline selector completion (legacy - skeleton only)
    const handleOutlinePlanReady = (plan, detailedOutline) => {
        setShowOutlineSelector(false);
        setCurrentPlan(plan);
        setShowPlanReview(true);
    };
    
    // Handle complete story from conductor (new - full story)
    const handleStoryComplete = async (finalStory, detailedOutline) => {
        setShowOutlineSelector(false);

        if (!finalStory) {
            console.error('Invalid story received from conductor: null');
            return;
        }

        let nodesDict = finalStory.nodes || {};
        if (Array.isArray(nodesDict)) {
            nodesDict = {};
            for (const node of finalStory.nodes) {
                if (node && node.id) {
                    nodesDict[node.id] = node;
                }
            }
        }

        if (Object.keys(nodesDict).length === 0) {
            console.error('Invalid story received from conductor: no nodes');
            return;
        }

        try {
            const normalizeEffects = (effects) => {
                if (!effects || !Array.isArray(effects)) return effects;
                return effects.map(eff => {
                    if (eff.type === 'goto_node' && eff.target_node && !eff.target) {
                        return { ...eff, target: eff.target_node };
                    }
                    return eff;
                });
            };

            const newNodes = [];
            const editorNodesArray = [];

            for (const [nodeId, nodeData] of Object.entries(nodesDict)) {
                if (!nodeData) continue;

                const normalizedActions = (nodeData.actions || []).map(action => ({
                    ...action,
                    effects: normalizeEffects(action.effects)
                }));

                const normalizedObjects = (nodeData.objects || []).map(obj => ({
                    ...obj
                }));

                const normalizedTriggers = (nodeData.triggers || []).map(trigger => ({
                    ...trigger,
                    effects: normalizeEffects(trigger.effects)
                }));

                editorNodesArray.push({
                    id: nodeId,
                    ...nodeData,
                    actions: normalizedActions,
                    objects: normalizedObjects,
                    triggers: normalizedTriggers
                });

                newNodes.push({
                    id: nodeId,
                    type: viewMode === 'detailed' ? 'detailed' : 'default',
                    position: { x: 0, y: 0 },
                    data: {
                        ...nodeData,
                        id: nodeId,
                        name: nodeData.name || nodeId,
                        definition: nodeData.definition || '',
                        explicit_state: nodeData.explicit_state || '',
                        implicit_state: nodeData.implicit_state || '',
                        properties: nodeData.properties || {},
                        actions: normalizedActions,
                        objects: normalizedObjects,
                        triggers: normalizedTriggers,
                        viewMode: viewMode
                    }
                });
            }

            const newEdges = generateEdgesFromConnections(storyData, newNodes);
            const layouted = getLayoutedElements(newNodes, newEdges, 'LR', viewMode);
            const baseTitle = finalStory.title
                || detailedOutline?.title
                || activeImportDraft?.title
                || storyData?.title
                || storyData?.name
                || t('import.source.default');

            const persistedStory = buildGeneratedStoryPayload(finalStory, {
                title: baseTitle,
                fallbackId: storyId || generateStoryId(baseTitle),
                importDraft: activeImportDraft
            });

            const nextStoryData = {
                ...persistedStory,
                nodes: editorNodesArray
            };

            try {
                const reviewResult = await reviewStory(persistedStory, false);
                if (reviewResult?.status && reviewResult.status !== 'ok') {
                    alert(`Imported story review: ${reviewResult.message}`);
                }
            } catch (reviewError) {
                console.warn('Story review failed:', reviewError);
            }

            let resolvedStoryId = storyId || persistedStory.id;
            if (!storyId) {
                try {
                    const created = await createStoryFromGenerated(persistedStory);
                    resolvedStoryId = created.storyId;
                    persistedStory.id = created.storyId;
                    nextStoryData.id = created.storyId;
                    nextStoryData.name = nextStoryData.name || baseTitle;
                    nextStoryData.title = nextStoryData.title || baseTitle;
                    skipLoadRef.current = true;
                    setStoryId(created.storyId);
                    setLoadedFrom('original');
                    setTempPath(null);
                    await refreshStories();
                } catch (createError) {
                    console.warn('Auto-create failed, keeping story local until save:', createError);
                    skipLoadRef.current = true;
                    setStoryId(resolvedStoryId);
                    setLoadedFrom('new');
                }
            }

            setNodes(layouted.nodes);
            setEdges(layouted.edges);
            setStoryData({
                ...nextStoryData,
                id: resolvedStoryId,
                title: nextStoryData.title || baseTitle,
                name: nextStoryData.name || baseTitle,
                start_node_id: nextStoryData.start_node_id || 'start'
            });
            clearHistory(layouted.nodes, layouted.edges);
            setShowLoadingPanel(false);
            setActiveImportDraft(null);

            setTimeout(() => {
                if (reactFlowInstance) {
                    reactFlowInstance.fitView({ padding: 0.2 });
                }
            }, 100);

            console.log('Story created successfully with', layouted.nodes.length, 'nodes and', layouted.edges.length, 'edges');
        } catch (err) {
            console.error('Error processing story:', err);
            alert(`Failed to prepare imported story: ${err.message}`);
        }
    };

    // Handle real-time node creation/update during story conducting
    const handleConductorNodeCreated = (nodeId, nodeData) => {
        if (!nodeId || !nodeData) return;
        
        // Normalize effects: convert "target_node" to "target" for goto_node effects
        const normalizeEffects = (effects) => {
            if (!effects || !Array.isArray(effects)) return effects;
            return effects.map(eff => {
                if (eff.type === 'goto_node' && eff.target_node && !eff.target) {
                    return { ...eff, target: eff.target_node };
                }
                return eff;
            });
        };
        
        const normalizedActions = (nodeData.actions || []).map(action => ({
            ...action,
            effects: normalizeEffects(action.effects)
        }));
        
        const normalizedObjects = (nodeData.objects || []).map(obj => ({
            ...obj
        }));
        
        const normalizedTriggers = (nodeData.triggers || []).map(trigger => ({
            ...trigger,
            effects: normalizeEffects(trigger.effects)
        }));
        
        setNodes(prevNodes => {
            // Check if node already exists
            const existingIndex = prevNodes.findIndex(n => n.id === nodeId);
            
            const rfNode = {
                id: nodeId,
                type: viewMode === 'detailed' ? 'detailed' : 'default',
                position: existingIndex >= 0 
                    ? prevNodes[existingIndex].position 
                    : { x: 100 + (prevNodes.length % 5) * 250, y: 100 + Math.floor(prevNodes.length / 5) * 200 },
                data: {
                    ...nodeData,
                    id: nodeId,
                    name: nodeData.name || nodeId,
                    definition: nodeData.definition || '',
                    explicit_state: nodeData.explicit_state || '',
                    implicit_state: nodeData.implicit_state || '',
                    properties: nodeData.properties || {},
                    actions: normalizedActions,
                    objects: normalizedObjects,
                    triggers: normalizedTriggers,
                    viewMode: viewMode
                }
            };
            
            let updatedNodes;
            if (existingIndex >= 0) {
                // Update existing node
                updatedNodes = [...prevNodes];
                updatedNodes[existingIndex] = rfNode;
            } else {
                // Add new node
                updatedNodes = [...prevNodes, rfNode];
            }
            
            const newEdges = generateEdgesFromConnections(storyData, updatedNodes);
            setEdges(newEdges);
            
            return updatedNodes;
        });
    };

    // Wrapper that routes to the appropriate AI handler
    const handleLlmSubmitWrapper = async () => {
        if (usePlanBasedAI) {
            await handlePlanBasedAISubmit();
        } else if (useStreamingAI) {
            await handleStreamingAISubmit();
        } else {
            await handleLegacyAISubmit();
        }
    };

    return (
        <div className="app">
            <div className="header">
                <h1>{t('app.title')}</h1>
                <MenuBar
                    onNewStory={handleNewStory}
                    onSaveStory={saveStoryWrapper}
                    onLoadStory={handleLoadStory}
                    stories={stories}
                    currentStoryId={storyId}
                    onUndo={performUndo}
                    onRedo={performRedo}
                    canUndo={canUndo}
                    canRedo={canRedo}
                    viewMode={viewMode}
                    onViewModeChange={handleViewModeChange}
                    onOpenCharacterPanel={() => setShowCharacterPanel(true)}
                    unsavedCount={unsavedCount}
                    onShowVersionHistory={() => setShowVersionHistory(true)}
                    graphStatus={graphStatus}
                    onCompileGraph={handleCompileGraph}
                    graphCompileLoading={graphCompileLoading}
                />
                <span className={`loaded-from-indicator ${loadedFrom}`}>
                    {t('app.loadedFrom', { source: t(`app.loadedFrom.${loadedFrom}`) })}
                </span>
            </div>
            <div className="main-content">
                <div className="ai-assistant">
                    {!isAiPanelOpen ? (
                        <button className="ai-toggle-btn" onClick={() => setIsAiPanelOpen(true)}>
                            <span className="ai-label">
                                {selectedNodeCount > 0
                                    ? t('app.aiSelectedCount', { count: selectedNodeCount })
                                    : t('app.aiTitle')}
                            </span>
                        </button>
                    ) : (
                        <div className="ai-assistant-panel">
                            <div className="ai-header">
                                <span>{t('app.aiTitle')}</span>
                                <div className="ai-mode-toggle">
                                    <label className="ai-mode-label" title={t('app.aiModeTooltip')}>
                                        <input
                                            type="checkbox"
                                            checked={usePlanBasedAI}
                                            onChange={(e) => setUsePlanBasedAI(e.target.checked)}
                                            disabled={llmLoading}
                                        />
                                        <span className="ai-mode-text">{usePlanBasedAI ? t('app.aiModePlan') : t('app.aiModeDirect')}</span>
                                    </label>
                                </div>
                                <button className="ai-close-btn" onClick={() => setIsAiPanelOpen(false)}>×</button>
                            </div>
                            <div className="ai-content">
                                {/* Context indicator based on selection */}
                                {selectedNodeCount > 0 ? (
                                    <div className="selected-nodes-info">
                                        <span className="selected-nodes-count">{t('assistant.selectedCount', { count: selectedNodeCount })}</span>
                                        <span>{nodes.filter(n => n.selected).map(n => n.data?.name || n.id).join(', ')}</span>
                                    </div>
                                ) : nodes.length <= 1 ? (
                                    <div className="ai-context-info ai-context-new-story">
                                        <p>{t('app.aiNoStoryContext')}</p>
                                    </div>
                                ) : (
                                    <div className="ai-context-info">
                                        <p>{t('app.aiNoSelectionContext')}</p>
                                    </div>
                                )}
                                <textarea
                                    value={llmPrompt}
                                    onChange={(e) => setLlmPrompt(e.target.value)}
                                    placeholder={nodes.length <= 1 
                                        ? t('app.aiPromptPlaceholder.new')
                                        : t('app.aiPromptPlaceholder.edit')}
                                    autoFocus
                                    disabled={llmLoading}
                                />
                                {llmLoading && aiThinkingMessage && (
                                    <div className="ai-thinking-indicator">
                                        <div className="ai-thinking-spinner"></div>
                                        <span className="ai-thinking-message">{aiThinkingMessage}</span>
                                    </div>
                                )}
                                <button
                                    className={`ai-submit-btn ${llmLoading ? 'loading' : ''}`}
                                    onClick={handleLlmSubmitWrapper}
                                    disabled={llmLoading || !llmPrompt}
                                >
                                    {llmLoading ? (useStreamingAI ? t('app.aiWorking') : t('app.aiProcessing')) : t('app.aiSubmit')}
                                </button>
                            </div>
                        </div>
                    )}
                </div>
                {
                    !showLoadingPanel && (loading || nodes.length === 0) ? (
                        <div className="loading-pane">{t('app.loadingStory')}</div>
                    ) : !showLoadingPanel && (
                        <>
                            <div className="graph-view-wrapper" ref={reactFlowWrapper}>
                                <ReactFlow
                                    nodes={nodes}
                                    edges={edgesWithHighlight}
                                    onNodesChange={onNodesChangeWithHistory}
                                    onEdgesChange={onEdgesChange}
                                    onConnect={onConnect}
                                    onEdgeClick={handleEdgeClick}
                                    onEdgesDelete={handleEdgesDelete}
                                    onNodeDoubleClick={(event, node) => {
                                        event.preventDefault();
                                        setSelectedNode(node);
                                        setSelectedConnectionId(null);
                                        setShowCharacterPanel(false);
                                    }}
                                    onNodeMouseEnter={(event, node) => setHoveredNodeId(node.id)}
                                    onNodeMouseLeave={() => setHoveredNodeId(null)}
                                    onNodeContextMenu={handleNodeContextMenu}
                                    onPaneContextMenu={handlePaneContextMenu}
                                    onPaneClick={handlePaneClick}
                                    onInit={setReactFlowInstance}
                                    panOnDrag={[2]}
                                    selectionOnDrag
                                    fitView
                                    nodeTypes={nodeTypes}
                                    edgeTypes={edgeTypes}
                                >
                                    <Controls />
                                </ReactFlow>
                                {contextMenu && (
                                    <ContextMenu
                                        x={contextMenu.x}
                                        y={contextMenu.y}
                                        nodeId={contextMenu.nodeId}
                                        onCopy={handleCopyNode}
                                        onPaste={handlePasteNode}
                                        onDelete={handleDeleteNode}
                                        onAddNode={handleAddNode}
                                        onAddPseudoNode={handleAddPseudoNode}
                                        onAddGenerateNode={handleAddGenerateNode}
                                        onConvertPseudoNodes={handleBatchConvertWrapper}
                                        hasPseudoNodes={nodes.some(n => n.type === 'pseudo')}
                                        onGroup={handleGroupNodes}
                                        onUngroup={handleUngroupNodes}
                                        selectedNodeCount={nodes.filter(n => n.selected).length}
                                        isGroupSelected={nodes.filter(n => n.selected && n.type === 'group').length > 0}
                                        onClose={() => setContextMenu(null)}
                                        canPaste={!!copiedNode}
                                    />
                                )}
                            </div>
                            {selectedNode && !showCharacterPanel && (
                                <div className="editors-container">
                                    <NodeEditor
                                        node={selectedNode}
                                        onNodeChange={handleNodeChange}
                                        onNodeClose={() => setSelectedNode(null)}
                                        onShapeClick={handleShapeClick}
                                        onSecondaryClose={() => {
                                            setSecondaryEditorOpen(false);
                                            setSelectedShape(null);
                                        }}
                                        selectedShape={selectedShape}
                                        secondaryEditorOpen={secondaryEditorOpen}
                                        shifted={secondaryEditorOpen}
                                        availableCharacters={storyData.characters || []}
                                        onUpdateCharacters={handleUpdateCharacters}
                                        onEditCharacter={handleEditCharacter}
                                    />
                                    <SecondaryEditor
                                        isOpen={secondaryEditorOpen}
                                        selectedShape={selectedShape}
                                        onUpdateShape={handleUpdateShape}
                                        onClose={() => setSecondaryEditorOpen(false)}
                                    />
                                </div>
                            )}

                            {selectedConnection && (
                                <div className="edge-inspector-panel">
                                    <div className="edge-inspector-header">
                                        <h3>Connection Edge</h3>
                                        <button
                                            type="button"
                                            className="btn btn-secondary"
                                            onClick={() => setSelectedConnectionId(null)}
                                        >
                                            Close
                                        </button>
                                    </div>
                                    <div className="edge-inspector-meta">
                                        <span>{selectedConnection.source} -> {(selectedConnection.targets || []).join(', ')}</span>
                                    </div>
                                    <label className="edge-inspector-label">
                                        Connection ID
                                        <textarea
                                            value={selectedConnection.id || ''}
                                            onChange={(event) => handleConnectionIdChange(event.target.value)}
                                            placeholder="Use a short, distinguishable ID like forest_path_to_deep_forest."
                                        />
                                    </label>
                                    <div className="edge-inspector-actions">
                                        <button
                                            type="button"
                                            className="btn btn-danger"
                                            onClick={handleDeleteSelectedConnection}
                                        >
                                            Delete Edge
                                        </button>
                                    </div>
                                </div>
                            )}

                            {showCharacterPanel && (
                                <div className="editors-container expanded">
                                    <CharacterPanel
                                        isOpen={showCharacterPanel}
                                        onClose={() => {
                                            setShowCharacterPanel(false);
                                            setEditingCharacterId(null);
                                        }}
                                        characters={storyData?.characters || []}
                                        onUpdateCharacters={handleUpdateCharacters}
                                        nodes={storyData?.nodes || {}}
                                        initialCharId={editingCharacterId}
                                        storyData={storyData}
                                    />
                                </div>
                            )}

                            {showParameterPanel && (
                                <div className="editors-container expanded">
                                    <ParameterPanel
                                        isOpen={showParameterPanel}
                                        onClose={() => setShowParameterPanel(false)}
                                        parameters={storyData?.initial_variables || {}}
                                        onUpdateParameters={(newParams) => {
                                            setStoryData(prev => ({
                                                ...prev,
                                                initial_variables: newParams
                                            }));
                                        }}
                                        storyData={storyData}
                                    />
                                </div>
                            )}

                            {showLorePanel && (
                                <div className="editors-container expanded">
                                    <LorePanel
                                        isOpen={showLorePanel}
                                        onClose={() => setShowLorePanel(false)}
                                        parameters={storyData?.initial_variables || {}}
                                        onUpdateParameters={(newParams) => {
                                            setStoryData(prev => ({
                                                ...prev,
                                                initial_variables: newParams
                                            }));
                                        }}
                                        storyData={storyData}
                                    />
                                </div>
                            )}

                            {showObjectPanel && (
                                <div className="editors-container expanded">
                                    <ObjectPanel
                                        isOpen={showObjectPanel}
                                        onClose={() => setShowObjectPanel(false)}
                                        objects={storyData?.objects || []}
                                        onUpdateObjects={(newObjects) => {
                                            setStoryData(prev => ({
                                                ...prev,
                                                objects: newObjects
                                            }));
                                        }}
                                        storyData={storyData}
                                    />
                                </div>
                            )}
                        </>
                    )
                }

                <FloatingToolPanel
                    onOpenCharacters={() => {
                        setShowCharacterPanel(true);
                        setShowParameterPanel(false);
                        setShowLorePanel(false);
                        setShowObjectPanel(false);
                        setSelectedNode(null);
                    }}
                    onOpenParameters={() => {
                        setShowParameterPanel(true);
                        setShowCharacterPanel(false);
                        setShowLorePanel(false);
                        setShowObjectPanel(false);
                        setSelectedNode(null);
                    }}
                    onOpenLore={() => {
                        setShowLorePanel(true);
                        setShowCharacterPanel(false);
                        setShowParameterPanel(false);
                        setShowObjectPanel(false);
                        setSelectedNode(null);
                    }}
                    onOpenObjects={() => {
                        setShowObjectPanel(true);
                        setShowCharacterPanel(false);
                        setShowParameterPanel(false);
                        setShowLorePanel(false);
                        setSelectedNode(null);
                    }}
                />
            </div >

            <VersionHistoryDialog
                isOpen={showVersionHistory}
                onClose={() => setShowVersionHistory(false)}
                storyId={storyId}
                getVersions={getVersions}
                onRestore={handleRestoreVersion}
            />

            <ConfirmDialog
                isOpen={confirmDialog.isOpen}
                onSaveAndContinue={handleConfirmSave}
                onDontSave={handleConfirmDontSave}
                onCancel={handleConfirmCancel}
            />

            <InputDialog
                isOpen={inputDialog.isOpen}
                title={t('loading.newStoryTitle')}
                message={t('loading.newStoryMessage')}
                placeholder={t('loading.newStoryPlaceholder')}
                confirmText={t('loading.create')}
                onConfirm={handleInputDialogConfirm}
                onCancel={handleInputDialogCancel}
            />

            {showLoadingPanel && (
                <LoadingPanel
                    onCreateNew={handleLoadingPanelCreate}
                    onLoadStory={handleLoadingPanelLoad}
                    onOpenImport={handleLoadingPanelImport}
                    stories={stories}
                />
            )}

            <ImportWizard
                isOpen={showImportWizard}
                onClose={() => setShowImportWizard(false)}
                onConversionReady={handleImportConversionReady}
            />

            {/* Plan Review Panel */}
            <PlanReviewPanel
                isOpen={showPlanReview}
                plan={currentPlan}
                onExecute={handleExecutePlan}
                onCancel={() => {
                    setShowPlanReview(false);
                    setCurrentPlan(null);
                }}
                isExecuting={planExecuting}
                currentStep={planCurrentStep}
                executionProgress={planProgress}
            />

            {/* Outline Selector for Story Creation Wizard */}
            <OutlineSelector
                isOpen={showOutlineSelector}
                onClose={() => {
                    setShowOutlineSelector(false);
                    // Reset wizard initial state
                    setWizardInitialIdea('');
                    setWizardInitialPhase(null);
                    setWizardInitialOutlines([]);
                    setWizardInitialDetailedOutline(null);
                    setWizardInitialPlan(null);
                    setActiveImportDraft(null);
                }}
                onDetailedBack={activeImportDraft ? () => {
                    setShowOutlineSelector(false);
                    setShowImportWizard(true);
                } : null}
                onStoryComplete={handleStoryComplete}
                onPlanReady={handleOutlinePlanReady}
                onNodeCreated={handleConductorNodeCreated}
                generateOutlines={handleWizardGenerateOutlines}
                expandOutline={handleWizardExpandOutline}
                refineOutline={refineOutline}
                refineOutlines={refineOutlines}
                refineDetailedOutline={refineDetailedOutline}
                executePlan={executePlan}
                conductStory={conductStory}
                initialIdea={wizardInitialIdea}
                initialPhase={wizardInitialPhase}
                initialOutlines={wizardInitialOutlines}
                initialDetailedOutline={wizardInitialDetailedOutline}
                initialPlan={wizardInitialPlan}
            />
        </div >
    );
};

const App = () => (
    <ReactFlowProvider>
        <AppContent />
    </ReactFlowProvider>
);

export default App;
