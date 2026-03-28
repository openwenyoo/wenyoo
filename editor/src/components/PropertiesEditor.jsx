import React, { useState } from 'react';
import { useLocale } from '../i18n';

/**
 * Reusable key-value editor for the `properties` dict
 * Used in NodeEditor, ObjectEditor, CharacterPanel
 */
const PropertiesEditor = ({ properties = {}, onChange }) => {
    const [newKey, setNewKey] = useState('');
    const { t } = useLocale();
    const entries = Object.entries(properties);

    const addEntry = () => {
        if (!newKey.trim()) return;
        const key = newKey.trim();
        if (properties.hasOwnProperty(key)) {
            alert(t('properties.exists', { key }));
            return;
        }
        onChange({ ...properties, [key]: '' });
        setNewKey('');
    };

    const removeEntry = (key) => {
        const { [key]: _, ...rest } = properties;
        onChange(rest);
    };

    const updateKey = (oldKey, newKeyName) => {
        if (oldKey === newKeyName) return;
        if (properties.hasOwnProperty(newKeyName)) {
            alert(t('properties.exists', { key: newKeyName }));
            return;
        }
        const { [oldKey]: value, ...rest } = properties;
        onChange({ ...rest, [newKeyName]: value });
    };

    const updateValue = (key, newValue) => {
        // Try to parse as JSON for complex values, otherwise keep as string
        let parsedValue = newValue;
        if (newValue === 'true') parsedValue = true;
        else if (newValue === 'false') parsedValue = false;
        else if (/^-?\d+$/.test(newValue)) parsedValue = parseInt(newValue, 10);
        else if (/^-?\d+\.\d+$/.test(newValue)) parsedValue = parseFloat(newValue);
        
        onChange({ ...properties, [key]: parsedValue });
    };

    const formatValue = (value) => {
        if (typeof value === 'object') return JSON.stringify(value);
        return String(value);
    };

    return (
        <div className="properties-editor">
            {entries.length > 0 ? (
                <div className="properties-list">
                    {entries.map(([key, value]) => (
                        <div key={key} className="property-row">
                            <input
                                className="property-key"
                                value={key}
                                onChange={(e) => updateKey(key, e.target.value)}
                                placeholder={t('properties.keyPlaceholder')}
                            />
                            <input
                                className="property-value"
                                value={formatValue(value)}
                                onChange={(e) => updateValue(key, e.target.value)}
                                placeholder={t('properties.valuePlaceholder')}
                            />
                            <button 
                                className="property-remove-btn"
                                onClick={() => removeEntry(key)}
                                title={t('properties.remove')}
                            >×</button>
                        </div>
                    ))}
                </div>
            ) : (
                <div className="empty-state">{t('properties.empty')}</div>
            )}
            <div className="property-add-row">
                <input
                    className="property-new-key"
                    value={newKey}
                    onChange={(e) => setNewKey(e.target.value)}
                    placeholder={t('properties.newPlaceholder')}
                    onKeyDown={(e) => e.key === 'Enter' && addEntry()}
                />
                <button 
                    className="add-button small"
                    onClick={addEntry}
                    title={t('properties.add')}
                >+</button>
            </div>
        </div>
    );
};

export default PropertiesEditor;
