import React, { memo } from 'react';
import { NodeResizer } from 'reactflow';
import '../styles/nodes.css';

const GroupNode = ({ data, selected }) => {
    const safeData = data || {};
    const displayLabel = safeData.groupId || safeData.label || 'Group';
    const previewText = (safeData.definition || '').trim().split('\n')[0];

    return (
        <div className={`group-node ${selected ? 'selected' : ''}`}>
            <NodeResizer
                minWidth={100}
                minHeight={100}
                isVisible={selected}
                lineClassName="group-node-resizer-line"
                handleClassName="group-node-resizer-handle"
            />
            <div className="group-node-header">
                <span className="group-node-label">
                    {displayLabel}
                </span>
            </div>
            <div className="group-node-content">
                {previewText && (
                    <div className="group-node-preview">
                        {previewText}
                    </div>
                )}
            </div>
        </div>
    );
};

export default memo(GroupNode);
