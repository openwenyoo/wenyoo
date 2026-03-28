import React, { useState } from 'react';
import { useLocale } from '../i18n';

/**
 * Editor for character memory array (DSPP model)
 * Each entry: { role: 'user'|'assistant'|'system', content: string }
 */
const MemoryEditor = ({ memory = [], onChange }) => {
    const [newRole, setNewRole] = useState('user');
    const [newContent, setNewContent] = useState('');
    const { t } = useLocale();

    const addEntry = () => {
        if (!newContent.trim()) return;
        onChange([...memory, { role: newRole, content: newContent.trim() }]);
        setNewContent('');
    };

    const removeEntry = (index) => {
        onChange(memory.filter((_, i) => i !== index));
    };

    const updateEntry = (index, field, value) => {
        const updated = [...memory];
        updated[index] = { ...updated[index], [field]: value };
        onChange(updated);
    };

    return (
        <div className="memory-editor">
            {memory.length > 0 ? (
                <div className="memory-list">
                    {memory.map((entry, index) => (
                        <div key={index} className="memory-entry">
                            <div className="memory-entry-header">
                                <select
                                    className="memory-role-select"
                                    value={entry.role || 'user'}
                                    onChange={(e) => updateEntry(index, 'role', e.target.value)}
                                >
                                    <option value="user">{t('memory.user')}</option>
                                    <option value="assistant">{t('memory.assistant')}</option>
                                    <option value="system">{t('memory.system')}</option>
                                </select>
                                <button 
                                    className="memory-remove-btn"
                                    onClick={() => removeEntry(index)}
                                    title={t('memory.remove')}
                                >×</button>
                            </div>
                            <textarea
                                className="memory-content"
                                value={entry.content || ''}
                                onChange={(e) => updateEntry(index, 'content', e.target.value)}
                                rows={2}
                                placeholder={t('memory.contentPlaceholder')}
                            />
                        </div>
                    ))}
                </div>
            ) : (
                <div className="empty-state">{t('memory.empty')}</div>
            )}
            <div className="memory-add-row">
                <select
                    className="memory-role-select"
                    value={newRole}
                    onChange={(e) => setNewRole(e.target.value)}
                >
                    <option value="user">{t('memory.user')}</option>
                    <option value="assistant">{t('memory.assistant')}</option>
                    <option value="system">{t('memory.system')}</option>
                </select>
                <input
                    className="memory-new-content"
                    value={newContent}
                    onChange={(e) => setNewContent(e.target.value)}
                    placeholder={t('memory.addPlaceholder')}
                    onKeyDown={(e) => e.key === 'Enter' && addEntry()}
                />
                <button 
                    className="add-button small"
                    onClick={addEntry}
                    title={t('memory.add')}
                >+</button>
            </div>
        </div>
    );
};

export default MemoryEditor;
