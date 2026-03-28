import React, { useState } from 'react';
import AIAssistant from './AIAssistant';
import PropertiesEditor from './PropertiesEditor';
import { streamAIEdit, EDIT_MODES, AI_SOURCES } from '../services/aiService';
import { useLocale } from '../i18n';

const ObjectPanel = ({ isOpen, onClose, objects = [], onUpdateObjects, storyData }) => {
    const [expandedIds, setExpandedIds] = useState(new Set());
    const [showAI, setShowAI] = useState(false);
    const [aiThinking, setAiThinking] = useState(false);
    const [aiMessage, setAiMessage] = useState('');
    const [showImplicitStateIds, setShowImplicitStateIds] = useState(new Set());
    const [showPropertiesIds, setShowPropertiesIds] = useState(new Set());
    const { t } = useLocale();

    if (!isOpen) return null;

    const sanitizeObject = (obj = {}) => ({
        id: obj.id || '',
        name: obj.name || '',
        definition: obj.definition || '',
        explicit_state: obj.explicit_state || '',
        implicit_state: obj.implicit_state || '',
        properties: obj.properties || {},
    });

    const toggleExpanded = (id) => {
        setExpandedIds(prev => {
            const next = new Set(prev);
            if (next.has(id)) {
                next.delete(id);
            } else {
                next.add(id);
            }
            return next;
        });
    };

    const handleAIRequest = async (prompt) => {
        setAiThinking(true);
        setAiMessage('Starting...');
        
        let addedCount = 0;
        let updatedCount = 0;
        let deletedCount = 0;
        let currentObjects = objects.map(sanitizeObject);

        await streamAIEdit({
            prompt,
            mode: EDIT_MODES.OBJECTS,
            objects: objects,
            storyData: storyData,
            source: AI_SOURCES.OBJECT_PANEL,

            onThinking: (message) => {
                setAiMessage(message);
            },

            onFunctionCall: (functionName, args) => {
                setAiMessage(`Calling ${functionName}...`);
            },

            onObjectCreated: (obj) => {
                addedCount++;
                currentObjects = [...currentObjects, sanitizeObject(obj)];
                onUpdateObjects(currentObjects);
                // Expand the newly created object
                setExpandedIds(prev => new Set(prev).add(obj.id));
            },

            onObjectUpdated: (obj, updatedFields) => {
                updatedCount++;
                currentObjects = currentObjects.map(o => 
                    o.id === obj.id ? sanitizeObject({ ...o, ...obj }) : o
                );
                onUpdateObjects(currentObjects);
            },

            onObjectDeleted: (objectId) => {
                deletedCount++;
                currentObjects = currentObjects.filter(o => o.id !== objectId);
                onUpdateObjects(currentObjects);
            },

            onComplete: ({ message, summary }) => {
                setAiThinking(false);
                setAiMessage('');
                setShowAI(false);
                
                const summaryText = [
                    addedCount > 0 ? t('panel.summaryCreated', { count: addedCount }) : null,
                    updatedCount > 0 ? t('panel.summaryUpdated', { count: updatedCount }) : null,
                    deletedCount > 0 ? t('panel.summaryDeleted', { count: deletedCount }) : null
                ].filter(Boolean).join(', ');
                
                if (summaryText) {
                    alert(t('panel.aiComplete', { summary: summaryText }));
                } else {
                    alert(message || t('panel.aiCompleteNoChanges'));
                }
            },

            onError: (error) => {
                setAiThinking(false);
                setAiMessage('');
                alert(t('panel.aiError', { error }));
            }
        });
    };

    const updateObject = (id, updates) => {
        onUpdateObjects(objects.map(obj =>
            obj.id === id ? sanitizeObject({ ...obj, ...updates }) : obj
        ));
    };

    const handleAddObject = () => {
        const baseId = 'new_object';
        let id = baseId;
        let counter = 1;
        while (objects.some(o => o.id === id)) {
            id = `${baseId}_${counter}`;
            counter++;
        }
        const newObj = {
            id,
            name: t('object.newObject'),
            definition: '',
            explicit_state: '',
            implicit_state: '',
            properties: { status: [] },
        };
        onUpdateObjects([...objects, newObj]);
        setExpandedIds(prev => new Set(prev).add(id));
    };

    const handleDeleteObject = (id, e) => {
        e.stopPropagation();
        if (window.confirm(t('object.deleteConfirm'))) {
            onUpdateObjects(objects.filter(o => o.id !== id));
        }
    };

    const toggleImplicitState = (id) => {
        setShowImplicitStateIds(prev => {
            const next = new Set(prev);
            if (next.has(id)) {
                next.delete(id);
            } else {
                next.add(id);
            }
            return next;
        });
    };

    const toggleProperties = (id) => {
        setShowPropertiesIds(prev => {
            const next = new Set(prev);
            if (next.has(id)) {
                next.delete(id);
            } else {
                next.add(id);
            }
            return next;
        });
    };


    return (
        <div className="object-panel right-panel">
            <div className="panel-header">
                <h3>{t('panel.objects')}</h3>
                <div style={{ display: 'flex', gap: '8px' }}>
                    <button
                        className="header-ai-btn"
                        onClick={() => setShowAI(!showAI)}
                        title={t('panel.aiAssist')}
                        style={{ color: 'var(--color-primary)' }}
                    >
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <path d="M12 2L14.5 9.5L22 12L14.5 14.5L12 22L9.5 14.5L2 12L9.5 9.5L12 2Z" fill="currentColor" />
                        </svg>
                        {t('panel.ai')}
                    </button>
                    <button className="close-btn" onClick={onClose}>×</button>
                </div>
            </div>
            <AIAssistant
                isOpen={showAI}
                onClose={() => !aiThinking && setShowAI(false)}
                onGenerate={handleAIRequest}
                contextInfo={t('panel.manageGlobalObjects')}
                title={t('panel.objectAiTitle')}
                externalLoading={aiThinking}
                externalMessage={aiMessage}
            />


            <div className="object-list-container">
                {objects.map(obj => {
                    const isExpanded = expandedIds.has(obj.id);
                    const showImplicitState = showImplicitStateIds.has(obj.id);
                    const showProperties = showPropertiesIds.has(obj.id);
                    const safeObject = sanitizeObject(obj);
                    return (
                        <div key={safeObject.id} className={`object-item ${isExpanded ? 'expanded' : ''}`}>
                            <div className="object-header" onClick={() => toggleExpanded(obj.id)}>
                                <span className="expand-icon">{isExpanded ? '▼' : '▶'}</span>
                                <span className="object-id">{safeObject.id}</span>
                                <button
                                    className="object-delete-btn"
                                    onClick={(e) => handleDeleteObject(obj.id, e)}
                                    title={t('object.deleteTitle')}
                                >×</button>
                            </div>

                            {isExpanded && (
                                <div className="object-content">
                                    <div className="object-field">
                                        <label>{t('node.id')}</label>
                                        <input
                                            type="text"
                                            value={safeObject.id}
                                            onChange={(e) => {
                                                const newId = e.target.value;
                                                if (newId && !objects.some(o => o.id === newId && o.id !== safeObject.id)) {
                                                    onUpdateObjects(objects.map(o =>
                                                        o.id === safeObject.id ? sanitizeObject({ ...o, id: newId }) : o
                                                    ));
                                                }
                                            }}
                                            className="object-input"
                                        />
                                    </div>
                                    <div className="object-field">
                                        <label>{t('node.name')}</label>
                                        <input
                                            type="text"
                                            value={safeObject.name}
                                            onChange={(e) => updateObject(obj.id, { name: e.target.value })}
                                            className="object-input"
                                        />
                                    </div>
                                    <div className="object-field">
                                        <label>{t('node.definition')}</label>
                                        <textarea
                                            value={safeObject.definition}
                                            onChange={(e) => updateObject(obj.id, { definition: e.target.value })}
                                            className="state-description"
                                            placeholder={t('object.definitionPlaceholder')}
                                            rows={4}
                                        />
                                    </div>

                                    <div className="object-field">
                                        <label>{t('node.explicitState')}</label>
                                        <textarea
                                            value={safeObject.explicit_state}
                                            onChange={(e) => updateObject(obj.id, { explicit_state: e.target.value })}
                                            className="state-description"
                                            placeholder={t('object.explicitStatePlaceholder')}
                                            rows={3}
                                        />
                                    </div>

                                    <div className="section collapsible-section">
                                        <div className="section-header clickable" onClick={() => toggleImplicitState(obj.id)}>
                                            <h4>
                                                <span className="collapse-indicator">{showImplicitState ? '▼' : '▶'}</span>
                                                {t('object.implicitState')} <span className="field-hint">({t('object.implicitStateHint')})</span>
                                            </h4>
                                        </div>
                                        {showImplicitState && (
                                            <div className="object-field">
                                                <textarea
                                                    value={safeObject.implicit_state}
                                                    onChange={(e) => updateObject(obj.id, { implicit_state: e.target.value })}
                                                    className="state-description"
                                                    placeholder={t('object.implicitStatePlaceholder')}
                                                    rows={3}
                                                />
                                            </div>
                                        )}
                                    </div>

                                    <div className="section collapsible-section">
                                        <div className="section-header clickable" onClick={() => toggleProperties(obj.id)}>
                                            <h4>
                                                <span className="collapse-indicator">{showProperties ? '▼' : '▶'}</span>
                                                {t('object.properties')} <span className="field-hint">({t('object.propertiesHint')})</span>
                                            </h4>
                                        </div>
                                        {showProperties && (
                                            <PropertiesEditor
                                                properties={safeObject.properties}
                                                onChange={(newProps) => updateObject(obj.id, { properties: newProps })}
                                            />
                                        )}
                                    </div>
                                </div>
                            )}
                        </div>
                    );
                })}

                {objects.length === 0 && (
                    <div className="empty-state">
                        {t('object.noObjects')}
                    </div>
                )}

                <button className="add-object-btn" onClick={handleAddObject}>
                    {t('object.addObject')}
                </button>
            </div>
        </div>
    );
};

export default ObjectPanel;
