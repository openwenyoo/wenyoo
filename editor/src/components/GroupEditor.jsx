import React, { useEffect, useState } from 'react';
import { useLocale } from '../i18n';

const normalizeGroupId = (value) => (
    (value || '')
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9_]+/g, '_')
);

const GroupEditor = ({ node, onGroupChange, onClose }) => {
    const nodeData = node.data || {};
    const [groupId, setGroupId] = useState(nodeData.groupId || '');
    const [definition, setDefinition] = useState(nodeData.definition || '');
    const { t } = useLocale();

    useEffect(() => {
        const data = node.data || {};
        setGroupId(data.groupId || '');
        setDefinition(data.definition || '');
    }, [node]);

    const handleSave = () => {
        const normalizedId = normalizeGroupId(groupId);
        onGroupChange({
            id: node.id,
            ...node.data,
            groupId: normalizedId,
            label: normalizedId || 'group',
            definition,
        });
        if (normalizedId !== groupId) {
            setGroupId(normalizedId);
        }
    };

    useEffect(() => {
        const timer = setTimeout(() => {
            const currentData = node.data || {};
            if (
                (currentData.groupId || '') !== groupId ||
                (currentData.definition || '') !== definition
            ) {
                handleSave();
            }
        }, 400);

        return () => clearTimeout(timer);
    }, [groupId, definition, node.data]);

    return (
        <div className="node-editor">
            <div className="sticky-header">
                <h3>{groupId || t('group.editorTitle')}</h3>
                <button className="header-close-btn" onClick={onClose}>×</button>
            </div>
            <div className="editor-scroll-content">
                <div className="form-group">
                    <label>{t('group.id')}</label>
                    <input
                        value={groupId}
                        onChange={(event) => setGroupId(event.target.value)}
                        onBlur={handleSave}
                        placeholder={t('group.idPlaceholder')}
                    />
                </div>
                <div className="form-group">
                    <label>{t('group.description')}</label>
                    <textarea
                        className="notebook-textarea"
                        rows={10}
                        value={definition}
                        onChange={(event) => setDefinition(event.target.value)}
                        onBlur={handleSave}
                        placeholder={t('group.descriptionPlaceholder')}
                    />
                </div>
            </div>
        </div>
    );
};

export default GroupEditor;
