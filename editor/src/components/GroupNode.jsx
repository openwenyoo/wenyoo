import React, { memo, useState } from 'react';
import { Handle, Position, NodeResizer } from 'reactflow';
import '../styles/nodes.css';

const GroupNode = ({ data, selected }) => {
    // Defensive check for undefined data
    const safeData = data || {};
    const [isEditing, setIsEditing] = useState(false);
    const [label, setLabel] = useState(safeData.label || 'Group');

    const handleDoubleClick = (e) => {
        e.stopPropagation();
        setIsEditing(true);
    };

    const handleBlur = () => {
        setIsEditing(false);
        if (safeData.onChange) {
            safeData.onChange(label);
        }
    };

    const handleChange = (e) => {
        setLabel(e.target.value);
    };

    const handleKeyDown = (e) => {
        if (e.key === 'Enter') {
            handleBlur();
        }
    };

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
                {isEditing ? (
                    <input
                        type="text"
                        value={label}
                        onChange={handleChange}
                        onBlur={handleBlur}
                        onKeyDown={handleKeyDown}
                        autoFocus
                        className="group-node-input"
                    />
                ) : (
                    <span onDoubleClick={handleDoubleClick} className="group-node-label">
                        {label}
                    </span>
                )}
            </div>
            <div className="group-node-content">
                {/* Content area */}
            </div>
        </div>
    );
};

export default memo(GroupNode);
