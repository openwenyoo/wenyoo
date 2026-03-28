import React, { memo } from 'react';
import { Handle, Position } from 'reactflow';

const DetailedNode = ({ data, selected }) => {
    // Defensive check for undefined data
    if (!data) {
        return (
            <div className="detailed-node error-node">
                <div className="node-header">
                    <div className="node-title">INVALID NODE</div>
                </div>
            </div>
        );
    }
    
    const {
        label,
        definition,
        explicit_state,
        generatedDescription,
        generatedDescriptionPost,
        objects = [],
        actions = [],
        triggers = [],
        characters = [],
        onShapeClick
    } = data;
    
    // Truncate long text for display
    const truncateText = (text, maxLength = 300) => {
        if (!text) return '';
        const trimmed = text.trim();
        if (trimmed.length <= maxLength) return trimmed;
        return trimmed.substring(0, maxLength) + '...';
    };

    const handleShapeClick = (e, item, type) => {
        e.stopPropagation(); // Prevent node selection when clicking an item
        if (onShapeClick) {
            onShapeClick(item, type);
        }
    };

    return (
        <div className={`detailed-node ${selected ? 'selected' : ''}`}>
            {/* Target Handle (Top Left) */}
            <Handle
                type="target"
                position={Position.Left}
                className="handle-target"
                style={{ top: 15, left: -5 }}
            />

            <div className="node-header">
                {data.isStartNode && <span title="Start Node" style={{ marginRight: '5px' }}>⭐</span>}
                <div className="node-title">{(data.name || data.label || data.id).toUpperCase()}</div>
            </div>

            {data.viewMode === 'detailed' && (
                <div className="node-body">
                    {/* Explicit State - What player sees */}
                    {explicit_state && (
                        <div className="node-description node-explicit_state">
                            {truncateText(explicit_state)}
                        </div>
                    )}
                    
                    {/* Definition - Static rules (shown smaller) */}
                    {definition && !explicit_state && (
                        <div className="node-description node-definition">
                            {truncateText(definition, 200)}
                        </div>
                    )}
                    
                    {/* Generated Description Section (from LLM pre_enter trigger) */}
                    {generatedDescription && (
                        <div 
                            className="node-description generated-description" 
                            title={generatedDescription}
                        >
                            [pre_enter] {truncateText(generatedDescription)}
                        </div>
                    )}

                    {/* Generated Description Section (from LLM post_enter trigger) */}
                    {generatedDescriptionPost && (
                        <div 
                            className="node-description generated-description" 
                            title={generatedDescriptionPost}
                        >
                            [post_enter] {truncateText(generatedDescriptionPost)}
                        </div>
                    )}

                    {objects.length > 0 && (
                        <div className="mini-list-section">
                            <div className="mini-list">
                                {objects.map((obj, i) => (
                                    <div
                                        key={i}
                                        className="mini-item type-object"
                                        onClick={(e) => handleShapeClick(e, obj, 'object')}
                                    >
                                        {obj.name || obj.id}
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {actions.length > 0 && (
                        <div className="mini-list-section">
                            <div className="mini-list">
                                {actions.map((act, i) => (
                                    <div
                                        key={i}
                                        className="mini-item type-action"
                                        onClick={(e) => handleShapeClick(e, act, 'action')}
                                    >
                                        {act.name || act.text || act.id}
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {triggers.length > 0 && (
                        <div className="mini-list-section">
                            <div className="mini-list">
                                {triggers.map((trig, i) => (
                                    <div
                                        key={i}
                                        className="mini-item type-trigger"
                                        onClick={(e) => handleShapeClick(e, trig, 'trigger')}
                                    >
                                        {trig.name || trig.id}
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                </div>
            )}

            {characters.length > 0 && (
                <div
                    className="node-characters"
                    title={`Characters: ${characters.map(c => c.name || c.id).join(', ')}`}
                >
                    {characters.slice(0, 3).map((char, i) => (
                        <div key={i} className="character-avatar" title={char.name || char.id}>
                            {(char.name || char.id).charAt(0).toUpperCase()}
                        </div>
                    ))}
                    {characters.length > 3 && (
                        <div className="character-avatar more">+{characters.length - 3}</div>
                    )}
                </div>
            )}

            {/* Source Handle (Top Right) */}
            <Handle
                type="source"
                position={Position.Right}
                className="handle-source"
                style={{ top: 15, right: -5 }}
            />
        </div>
    );
};

export default memo(DetailedNode);
