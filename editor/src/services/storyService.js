import axios from 'axios';
import { getLayoutedElements, generateEdgesFromConnections } from '../utils/graphLayout.jsx';
import './editorApi';  // registers axios auth interceptor

/**
 * Extract LLM-generated descriptions from pre_enter and post_enter triggers.
 * Looks for llm_generate effects in each trigger type and returns the prompt.
 */
const extractGeneratedDescriptions = (triggers) => {
    if (!triggers || !Array.isArray(triggers)) {
        return { preEnterPrompt: null, postEnterPrompt: null };
    }

    const findPromptForTriggerType = (triggerType) => {
        const matchingTriggers = triggers.filter(
            (trigger) => trigger.type === triggerType && Array.isArray(trigger.effects)
        );

        for (const trigger of matchingTriggers) {
            const llmEffect = trigger.effects.find(
                (effect) => effect.type === 'llm_generate' || effect.effect === 'llm_generate'
            );

            if (llmEffect && llmEffect.prompt) {
                return llmEffect.prompt;
            }
        }

        return null;
    };

    return {
        preEnterPrompt: findPromptForTriggerType('pre_enter'),
        postEnterPrompt: findPromptForTriggerType('post_enter'),
    };
};

const GROUP_PREFIX = 'group_';
const GROUP_PADDING = 40;
const NODE_WIDTH = 250;
const DETAILED_NODE_HEIGHT = 400;
const SIMPLE_NODE_HEIGHT = 60;

const normalizeGroupId = (value) => (
    (value || '')
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9_]+/g, '_')
);

const buildVisualGroupNodes = (baseNodes, parameters = {}, viewMode = 'detailed') => {
    const groupMembers = new Map();
    const nextNodes = new Map(
        (baseNodes || []).map((node) => [node.id, { ...node, data: { ...(node.data || {}) } }])
    );
    const defaultHeight = viewMode === 'detailed' ? DETAILED_NODE_HEIGHT : SIMPLE_NODE_HEIGHT;

    for (const node of baseNodes || []) {
        const groupIds = Array.isArray(node.data?.groups) ? node.data.groups : [];
        const primaryGroupId = groupIds.find((groupId) => typeof groupId === 'string' && groupId.trim());
        if (!primaryGroupId) {
            continue;
        }
        if (!groupMembers.has(primaryGroupId)) {
            groupMembers.set(primaryGroupId, []);
        }
        groupMembers.get(primaryGroupId).push(node.id);
    }

    if (groupMembers.size === 0) {
        return Array.from(nextNodes.values());
    }

    const visualGroups = [];
    for (const [groupId, memberIds] of groupMembers.entries()) {
        const members = memberIds
            .map((memberId) => nextNodes.get(memberId))
            .filter(Boolean);
        if (members.length === 0) {
            continue;
        }

        const xMin = Math.min(...members.map((node) => node.position.x));
        const yMin = Math.min(...members.map((node) => node.position.y));
        const xMax = Math.max(...members.map((node) => node.position.x + (node.width || NODE_WIDTH)));
        const yMax = Math.max(...members.map((node) => node.position.y + (node.height || defaultHeight)));
        const groupPosition = {
            x: xMin - GROUP_PADDING,
            y: yMin - GROUP_PADDING,
        };
        const groupNodeId = `group_visual_${groupId}`;

        visualGroups.push({
            id: groupNodeId,
            type: 'group',
            position: groupPosition,
            style: {
                width: xMax - xMin + GROUP_PADDING * 2,
                height: yMax - yMin + GROUP_PADDING * 2,
                zIndex: -1,
            },
            data: {
                label: groupId,
                groupId,
                definition: parameters[`${GROUP_PREFIX}${groupId}`] || '',
            },
        });

        for (const member of members) {
            nextNodes.set(member.id, {
                ...member,
                parentNode: groupNodeId,
                extent: 'parent',
                position: {
                    x: member.position.x - groupPosition.x,
                    y: member.position.y - groupPosition.y,
                },
            });
        }
    }

    return [...Array.from(nextNodes.values()), ...visualGroups];
};

/**
 * Load story from API and transform into graph format
 */
export const loadStory = async (id, tempPath, viewMode, handleShapeClickFromNode) => {
    console.log("loadStory called with id:", id, "temp_path:", tempPath);

    const url = tempPath
        ? `/api/story/${id}?temp_path=${encodeURIComponent(tempPath)}`
        : `/api/story/${id}`;

    const response = await axios.get(url);
    console.log("Story loaded:", response.data);

    const data = response.data;
    if (!data || !data.nodes) {
        throw new Error('Invalid story data');
    }

    // Convert nodes to array if needed
    let nodesArray = Array.isArray(data.nodes)
        ? data.nodes
        : Object.keys(data.nodes).map(nodeId => ({ id: nodeId, ...data.nodes[nodeId] }));

    const storyWithNodesAsArray = { ...data, nodes: nodesArray };

    // Create initial nodes with character data
    const storyCharacters = data.characters || [];
    const initialNodes = storyWithNodesAsArray.nodes.map(node => {
        // Find characters currently located in this node
        const nodeCharacters = storyCharacters.filter(c =>
            c.properties?.location === node.id
        );
        
        // Extract LLM-generated descriptions from pre_enter and post_enter triggers
        const { preEnterPrompt, postEnterPrompt } = extractGeneratedDescriptions(node.triggers);
        
        return {
            id: node.id,
            type: 'detailed',
            data: {
                label: node.id,
                isStartNode: node.id === data.start_node || node.id === data.start_node_id,
                ...node,
                generatedDescription: preEnterPrompt,
                generatedDescriptionPost: postEnterPrompt,
                viewMode: viewMode,
                onShapeClick: handleShapeClickFromNode,
                characters: nodeCharacters,
                groups: Array.isArray(node.groups) ? node.groups : []
            },
            position: { x: 0, y: 0 }
        };
    });

    const initialEdges = generateEdgesFromConnections(storyWithNodesAsArray, initialNodes);

    // Inject characters into node data for visual indicators
    const characters = storyWithNodesAsArray.characters || [];
    storyWithNodesAsArray.nodes.forEach(node => {
        const nodeCharacters = characters.filter(c =>
            c.properties?.location === node.id
        );
        node.characters = nodeCharacters;
    });

    console.log("Initial Nodes:", initialNodes);
    console.log("Initial Edges:", initialEdges);

    // Apply layout
    const layouted = getLayoutedElements(initialNodes, initialEdges, 'LR', viewMode);
    const groupedNodes = buildVisualGroupNodes(layouted.nodes, data.initial_variables || {}, viewMode);
    console.log("Layouted Nodes:", layouted.nodes);
    console.log("Layouted Edges:", layouted.edges);

    return {
        storyData: storyWithNodesAsArray,
        nodes: groupedNodes,
        edges: layouted.edges,
        graphStatus: {
            currentConnectionGraphSourceMd5: data.current_connection_graph_source_md5 || null,
            connectionGraphSourceMd5: data.connection_graph_source_md5 || null,
            status: data.connection_graph_status || 'missing',
        },
        loadedFrom: tempPath ? 'temp' : 'original',
        tempPath: tempPath || null
    };
};

/**
 * Save story to API
 */
export const saveStory = async (storyId, nodes, storyData) => {
    const sanitizeObject = (obj = {}) => ({
        id: obj.id || '',
        name: obj.name || '',
        definition: obj.definition || '',
        explicit_state: obj.explicit_state || '',
        implicit_state: obj.implicit_state || '',
        properties: obj.properties || {},
    });

    const baseParameters = Object.fromEntries(
        Object.entries(storyData?.initial_variables || {}).filter(([key]) => !key.startsWith(GROUP_PREFIX))
    );
    const groupIdByVisualNodeId = new Map();
    const visualGroups = [];
    const seenGroupIds = new Set();

    nodes
        .filter((node) => node.type === 'group')
        .forEach((node, index) => {
            const rawGroupId = node.data?.groupId || node.data?.label || `group${index + 1}`;
            let resolvedGroupId = normalizeGroupId(rawGroupId) || `group${index + 1}`;
            while (seenGroupIds.has(resolvedGroupId)) {
                resolvedGroupId = `${resolvedGroupId}_${seenGroupIds.size + 1}`;
            }
            seenGroupIds.add(resolvedGroupId);
            groupIdByVisualNodeId.set(node.id, resolvedGroupId);
            baseParameters[`${GROUP_PREFIX}${resolvedGroupId}`] = node.data?.definition || '';
            visualGroups.push({
                nodeId: node.id,
                groupId: resolvedGroupId,
                x: node.position?.x || 0,
                y: node.position?.y || 0,
                width: Number(node.style?.width) || NODE_WIDTH,
                height: Number(node.style?.height) || DETAILED_NODE_HEIGHT,
            });
        });

    const resolveNodeGroupId = (node) => {
        if (node.parentNode && groupIdByVisualNodeId.has(node.parentNode)) {
            return groupIdByVisualNodeId.get(node.parentNode);
        }

        const absoluteX = node.parentNode
            ? (nodes.find((candidate) => candidate.id === node.parentNode)?.position?.x || 0) + (node.position?.x || 0)
            : (node.position?.x || 0);
        const absoluteY = node.parentNode
            ? (nodes.find((candidate) => candidate.id === node.parentNode)?.position?.y || 0) + (node.position?.y || 0)
            : (node.position?.y || 0);
        const nodeWidth = node.width || NODE_WIDTH;
        const nodeHeight = node.height || DETAILED_NODE_HEIGHT;

        const containingGroup = visualGroups.find((group) => (
            absoluteX >= group.x &&
            absoluteY >= group.y &&
            absoluteX + nodeWidth <= group.x + group.width &&
            absoluteY + nodeHeight <= group.y + group.height
        ));

        return containingGroup?.groupId || null;
    };

    // Convert nodes back to story format
    const nodesMap = {};
    nodes
        .filter((node) => node.type !== 'group')
        .forEach(node => {
            const derivedGroupId = resolveNodeGroupId(node);
            const cleanNodeData = {
                ...node.data,
                objects: (node.data.objects || []).map(sanitizeObject),
            };
            if (derivedGroupId) {
                cleanNodeData.groups = [derivedGroupId];
            } else {
                delete cleanNodeData.groups;
            }
            delete cleanNodeData.label;
            delete cleanNodeData.onShapeClick;
            delete cleanNodeData.generatedDescription;
            delete cleanNodeData.generatedDescriptionPost;
            delete cleanNodeData.viewMode;
            delete cleanNodeData.characters;
            delete cleanNodeData.isStartNode;
            nodesMap[node.id] = cleanNodeData;
    });

    const {
        current_connection_graph_source_md5,
        connection_graph_status,
        currentConnectionGraphSourceMd5,
        connectionGraphSourceMd5,
        ...baseStoryData
    } = storyData || {};

    const storyPayload = {
        ...baseStoryData,
        initial_variables: baseParameters,
        objects: (baseStoryData.objects || []).map(sanitizeObject),
        nodes: nodesMap
    };

    const response = await axios.post(`/api/story/${storyId}`, storyPayload);
    return response.data;
};

export const compileConnectionGraph = async (storyId, { tempPath = null, withLlm = false } = {}) => {
    const response = await axios.post(`/api/story/${storyId}/compile-connections`, {
        temp_path: tempPath,
        with_llm: withLlm,
        write: true,
    });
    return response.data;
};

/**
 * Backup original story when first loaded
 */
export const backupOriginal = async (storyId) => {
    try {
        const response = await axios.post(`/api/story/${storyId}/backup-original`);
        return response.data;
    } catch (error) {
        console.error("Error backing up original:", error);
        return { success: false };
    }
};

/**
 * Get list of available versions for a story
 */
export const getVersions = async (storyId) => {
    try {
        const response = await axios.get(`/api/story/${storyId}/versions`);
        return response.data.versions || [];
    } catch (error) {
        console.error("Error getting versions:", error);
        return [];
    }
};

/**
 * Get content of a specific version
 */
export const getVersion = async (storyId, version) => {
    try {
        const response = await axios.get(`/api/story/${storyId}/version/${version}`);
        return response.data;
    } catch (error) {
        console.error("Error getting version:", error);
        return null;
    }
};

/**
 * Restore a story to a specific version
 */
export const restoreVersion = async (storyId, version) => {
    try {
        const response = await axios.post(`/api/story/${storyId}/restore/${version}`);
        return response.data;
    } catch (error) {
        console.error("Error restoring version:", error);
        return { success: false, error: error.message };
    }
};

/**
 * Create a new empty story
 */
export const createNewStory = (title, viewMode, handleShapeClickFromNode) => {
    const id = title.toLowerCase().replace(/\s+/g, '_');
    const newStory = {
        id: id,
        title: title,
        start_node: 'start',
        nodes: {
            start: {
                id: 'start',
                name: 'Start Node',
                definition: '',
                explicit_state: 'The story begins here.',
                implicit_state: '',
                properties: {},
                groups: [],
                objects: [],
                actions: [],
                triggers: []
            }
        }
    };

    const nodesArray = [{ id: 'start', ...newStory.nodes.start }];
    const storyWithNodesAsArray = { ...newStory, nodes: nodesArray };

    const initialNodes = [{
        id: 'start',
        type: viewMode === 'detailed' ? 'detailed' : 'default',
        data: {
            label: 'start',
            isStartNode: true,
            ...newStory.nodes.start,
            onShapeClick: handleShapeClickFromNode
        },
        position: { x: 0, y: 0 }
    }];

    return {
        storyData: storyWithNodesAsArray,
        nodes: initialNodes,
        edges: [],
        storyId: id
    };
};

export const generateStoryId = (title = 'untitled_story') => (
    title
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '_')
        .replace(/^_+|_+$/g, '')
        || 'untitled_story'
);

const ensureNodesMap = (nodes) => {
    if (!nodes) return {};
    if (!Array.isArray(nodes)) return nodes;

    return nodes.reduce((acc, node) => {
        if (node?.id) {
            acc[node.id] = { ...node };
            delete acc[node.id].id;
        }
        return acc;
    }, {});
};

export const buildGeneratedStoryPayload = (finalStory, {
    title,
    fallbackId,
    importDraft = null,
} = {}) => {
    const nodesMap = ensureNodesMap(finalStory?.nodes);
    const resolvedTitle = title || finalStory?.title || finalStory?.name || 'Imported Story';
    const importMetadata = importDraft ? {
        sourceType: importDraft.sourceType,
        sourceFormat: importDraft.sourceFormat,
        filename: importDraft.metadata?.filename,
        importedAt: importDraft.metadata?.importedAt,
        parser: importDraft.metadata?.parser,
        originalTitle: importDraft.title,
        warnings: importDraft.importWarnings || [],
        metadata: importDraft.metadata || {},
    } : null;
    const importLoreVariables = importDraft ? {
        lore_import_summary: importDraft.summary || '',
        lore_import_scenario: importDraft.scenario || '',
        lore_import_world_info: (importDraft.worldInfo || [])
            .map(entry => `${entry.title || entry.name || (entry.keys || []).join(', ')}: ${entry.content || ''}`.trim())
            .filter(Boolean)
            .join('\n'),
    } : {};

    return {
        ...finalStory,
        id: finalStory?.id || fallbackId || generateStoryId(resolvedTitle),
        name: finalStory?.name || resolvedTitle,
        title: resolvedTitle,
        description: finalStory?.description || importDraft?.summary || '',
        start_node_id: finalStory?.start_node_id || finalStory?.start_node || 'start',
        nodes: nodesMap,
        initial_variables: {
            ...importLoreVariables,
            ...(finalStory?.initial_variables || {})
        },
        characters: finalStory?.characters || [],
        objects: finalStory?.objects || [],
        metadata: {
            ...(finalStory?.metadata || {}),
            ...(importMetadata ? { import: importMetadata } : {})
        }
    };
};

export const createStoryFromGenerated = async (storyPayload) => {
    const baseId = generateStoryId(storyPayload?.id || storyPayload?.title || storyPayload?.name);
    let storyId = baseId;

    for (let attempt = 0; attempt < 3; attempt += 1) {
        const payload = {
            ...storyPayload,
            id: storyId
        };
        const response = await axios.post('/api/story', payload);
        const result = response.data;

        if (result?.success) {
            return {
                storyId: result.story_id || storyId,
                response: result
            };
        }

        if (result?.error && /already exists/i.test(result.error)) {
            storyId = `${baseId}_${Date.now()}`;
            continue;
        }

        throw new Error(result?.error || 'Failed to create generated story');
    }

    throw new Error('Failed to create generated story after multiple attempts');
};
