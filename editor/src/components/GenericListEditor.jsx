import React from 'react';

export const GenericListEditor = ({ list, onListChange, listName }) => {
    const handleItemChange = (index, updatedItem) => {
        const newList = [...list];
        newList[index] = updatedItem;
        onListChange(newList);
    };

    const addItem = () => {
        onListChange([...list, {}]);
    };

    const removeItem = (index) => {
        const newList = [...list];
        newList.splice(index, 1);
        onListChange(newList);
    };

    return (
        <div>
            {(list || []).map((item, index) => (
                <div key={index} className="list-item-editor">
                    {Object.entries(item).map(([key, value]) => (
                        <div key={key} className="form-group">
                            <label>{key}</label>
                            <textarea
                                value={typeof value === 'object' ? JSON.stringify(value, null, 2) : value}
                                onChange={(e) => {
                                    let newValue = e.target.value;
                                    try {
                                        newValue = JSON.parse(newValue);
                                    } catch (error) { /* Ignore error, treat as string */ }
                                    handleItemChange(index, { ...item, [key]: newValue });
                                }}
                                rows={typeof value === 'object' ? 4 : 1}
                            />
                        </div>
                    ))}
                    <button className="remove-btn" onClick={() => removeItem(index)}>Remove</button>
                </div>
            ))}
            <button onClick={addItem}>Add {listName}</button>
        </div>
    );
};