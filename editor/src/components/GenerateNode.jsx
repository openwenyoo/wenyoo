import React, { memo } from 'react';
import { Handle, Position } from 'reactflow';
import '../App.css';

const GenerateNode = ({ data, isConnectable }) => {
    // Defensive check for undefined data
    if (!data) {
        return <div className="generate-node error-node">Invalid Node</div>;
    }
    
    return (
        <div className="generate-node">
            <Handle
                type="target"
                position={Position.Left}
                isConnectable={isConnectable}
                className="node-handle"
            />
            <div className="node-header">
                <div className="node-title">Generate Node</div>
                <div className="node-id">{data.id}</div>
            </div>
            <div className="node-body">
                <div className="input-group">
                    <label>Generation Prompt:</label>
                    <textarea
                        className="generate-prompt-input nodrag"
                        placeholder="Describe what should be generated here..."
                        value={data.generation_prompt || ''}
                        onChange={(evt) => data.onChange?.(evt.target.value)}
                    />
                </div>
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

export default memo(GenerateNode);
