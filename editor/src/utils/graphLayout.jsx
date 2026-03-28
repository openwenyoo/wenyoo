import React from 'react';
import * as dagre from 'dagre';
import { getBezierPath, MarkerType } from 'reactflow';

const buildPairKey = (source, target) => [source, target].sort().join('::');

export const generateEdgesFromConnections = (storyData, nodes) => {
    const nodeIds = new Set((nodes || []).map((node) => node.id));
    const connections = Array.isArray(storyData?.connections) ? storyData.connections : [];
    const pairCounts = new Map();
    const edges = [];

    connections.forEach((connection) => {
        const source = connection?.source;
        const targets = Array.isArray(connection?.targets) ? connection.targets : [];
        if (!source || !nodeIds.has(source)) {
            return;
        }

        targets.forEach((target) => {
            if (!target || !nodeIds.has(target)) {
                return;
            }

            const pairKey = buildPairKey(source, target);
            const pairIndex = pairCounts.get(pairKey) || 0;
            pairCounts.set(pairKey, pairIndex + 1);

            const direction = source <= target ? 1 : -1;
            const curvature = pairIndex === 0 ? 0.1 : 0.1 + (pairIndex * 0.08 * direction);
            const connectionId = connection.id || `${source}-${target}-${pairIndex}`;

            edges.push({
                id: `${connectionId}__${target}`,
                source,
                target,
                type: 'custom',
                markerEnd: { type: MarkerType.ArrowClosed },
                animated: false,
                data: {
                    curvature,
                    connectionId,
                },
            });
        });
    });

    return edges;
};

// --- Dagre layouting ---
const dagreGraph = new dagre.graphlib.Graph();
dagreGraph.setDefaultEdgeLabel(() => ({}));

/**
 * Layout nodes and edges using Dagre algorithm
 * @param {Array} nodes - React Flow nodes
 * @param {Array} edges - React Flow edges
 * @param {string} direction - Layout direction ('TB' or 'LR')
 * @param {string} viewMode - View mode ('default' or 'detailed')
 * @returns {Object} Object with layouted nodes and edges
 */
export const getLayoutedElements = (nodes, edges, direction = 'TB', viewMode = 'default') => {
    const isHorizontal = direction === 'LR';
    const isDetailed = viewMode === 'detailed';

    // Compact layout settings
    dagreGraph.setGraph({
        rankdir: direction,
        ranksep: isDetailed ? 60 : 50,
        nodesep: isDetailed ? 25 : 15
    });

    nodes.forEach((node) => {
        const width = 250;
        const height = isDetailed ? 400 : 60;
        dagreGraph.setNode(node.id, { width, height });
    });

    edges.forEach((edge) => {
        dagreGraph.setEdge(edge.source, edge.target);
    });

    dagre.layout(dagreGraph);

    nodes.forEach((node) => {
        const nodeWithPosition = dagreGraph.node(node.id);
        node.targetPosition = 'left';
        node.sourcePosition = 'right';

        const width = 250;
        const height = isDetailed ? 400 : 60;

        node.position = {
            x: nodeWithPosition.x - width / 2,
            y: nodeWithPosition.y - height / 2,
        };

        return node;
    });

    return { nodes, edges };
};

/**
 * Custom edge component - ComfyUI-style smooth bezier curves
 * Highlights connected edges when node is hovered
 */
export const CustomEdge = ({
    id,
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    style = {},
    markerEnd,
    data,
}) => {
    // ComfyUI-style smooth bezier curvature
    const curvature = data?.curvature ?? 0.3;

    const [edgePath] = getBezierPath({
        sourceX,
        sourceY,
        sourcePosition,
        targetX,
        targetY,
        targetPosition,
        curvature,
    });

    const isHighlighted = data?.highlighted;

    return (
        <>
            {/* Visible edge path */}
            <path
                id={id}
                className={`react-flow__edge-path ${isHighlighted ? 'highlighted' : ''}`}
                d={edgePath}
                style={style}
                markerEnd={markerEnd}
            />
        </>
    );
};


