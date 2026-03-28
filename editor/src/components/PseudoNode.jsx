import React, { memo } from 'react';
import { Handle, Position } from 'reactflow';
import '../App.css';

const PseudoNode = ({ data, isConnectable }) => {
    // Defensive check for undefined data
    if (!data) {
        return <div className="pseudo-node error-node">Invalid Node</div>;
    }
    
    return (
        <div className="pseudo-node">
            <Handle
                type="target"
                position={Position.Left}
                isConnectable={isConnectable}
                className="node-handle"
            />
            <div className="node-header">
                <div className="node-title">Pseudo Node</div>
            </div>
            <div className="node-body">
                <textarea
                    className="pseudo-prompt-input nodrag"
                    placeholder="Describe this node..."
                    value={data.prompt || ''}
                    onChange={(evt) => data.onChange?.(evt.target.value)}
                />
            </div>
            <Handle
                type="source"
                position={Position.Right}
                isConnectable={isConnectable}
                className="node-handle"
            />
        </div>
    );
};

export default memo(PseudoNode);
