import React, { useState } from 'react';

const EffectEditor = ({ effect = {}, onChange, onRemove }) => {
    const [type, setType] = useState(effect.type || '');
    const [details, setDetails] = useState(effect || {});

    const handleTypeChange = (e) => {
        const newType = e.target.value;
        setType(newType);
        onChange({ ...details, type: newType });
    };

    const handleDetailChange = (key, value) => {
        const updated = { ...details, [key]: value };
        setDetails(updated);
        onChange(updated);
    };

    const renderFields = () => {
        switch (type) {
            case 'display_text':
                return (
                    <>
                        <div className="form-group">
                            <label>Text</label>
                            <textarea
                                value={details.text || ''}
                                onChange={(e) => handleDetailChange('text', e.target.value)}
                            />
                        </div>
                        <div className="form-group">
                            <label>Speaker (optional)</label>
                            <input
                                value={details.speaker || ''}
                                onChange={(e) => handleDetailChange('speaker', e.target.value)}
                            />
                        </div>
                    </>
                );
            case 'goto_node':
                return (
                    <div className="form-group">
                        <label>Target Node ID</label>
                        <input
                            value={details.target || ''}
                            onChange={(e) => handleDetailChange('target', e.target.value)}
                        />
                    </div>
                );
            case 'set_variable':
                return (
                    <>
                        <div className="form-group">
                            <label>Target Variable</label>
                            <input
                                value={details.target || ''}
                                onChange={(e) => handleDetailChange('target', e.target.value)}
                            />
                        </div>
                        <div className="form-group">
                            <label>Value</label>
                            <input
                                value={details.value || ''}
                                onChange={(e) => handleDetailChange('value', e.target.value)}
                            />
                        </div>
                    </>
                );
            case 'add_to_inventory':
            case 'remove_from_inventory':
                return (
                    <div className="form-group">
                        <label>Item ID</label>
                        <input
                            value={details.value || ''}
                            onChange={(e) => handleDetailChange('value', e.target.value)}
                        />
                    </div>
                );
            // Add more effect types as needed
            default:
                return <p>Select an effect type</p>;
        }
    };

    return (
        <div className="list-item-editor">
            <div className="sticky-sub-subsection-header">Effect Details</div>
            <div className="form-group">
                <label>Type</label>
                <select value={type} onChange={handleTypeChange}>
                    <option value="">Select Type</option>
                    <option value="display_text">Display Text</option>
                    <option value="goto_node">Goto Node</option>
                    <option value="set_variable">Set Variable</option>
                    <option value="add_to_inventory">Add to Inventory</option>
                    <option value="remove_from_inventory">Remove from Inventory</option>
                    {/* Add more options based on format */}
                </select>
            </div>
            {renderFields()}
            <button className="remove-btn" onClick={onRemove}>Remove Effect</button>
        </div>
    );
};

export default EffectEditor;