import React, { useState, useEffect } from 'react';
import AIAssistant from './AIAssistant';
import PropertiesEditor from './PropertiesEditor';
import { handleLlmSubmit } from '../services/aiService';
import { useLocale } from '../i18n';

const NodeEditor = ({ node, onNodeChange, onNodeClose, onShapeClick, onSecondaryClose, selectedShape, secondaryEditorOpen, shifted, availableCharacters, onUpdateCharacters, onEditCharacter }) => {
    const nodeData = node.data || {};
    const [id, setId] = useState(node.id || '');
    const [name, setName] = useState(nodeData.name || '');
    // DSPP model fields
    const [definition, setDefinition] = useState(nodeData.definition || '');
    const [explicit_state, setExplicitState] = useState(nodeData.explicit_state || '');
    const [implicit_state, setImplicitState] = useState(nodeData.implicit_state || '');
    const [properties, setProperties] = useState(nodeData.properties || {});
    const [objects, setObjects] = useState(nodeData.objects || []);
    const [actions, setActions] = useState(nodeData.actions || []);
    const [triggers, setTriggers] = useState(nodeData.triggers || []);

    const [showAI, setShowAI] = useState(false);
    const [showImplicitState, setShowImplicitState] = useState(false);
    const [showProperties, setShowProperties] = useState(false);
    const { t } = useLocale();

    useEffect(() => {
        const nodeData = node.data || {};
        setId(node.id || '');
        setName(nodeData.name || '');
        setDefinition(nodeData.definition || '');
        setExplicitState(nodeData.explicit_state || '');
        setImplicitState(nodeData.implicit_state || '');
        setProperties(nodeData.properties || {});
        setObjects(nodeData.objects || []);
        setActions(nodeData.actions || []);
        setTriggers(nodeData.triggers || []);
    }, [node]);

    const handleSave = () => {
        onNodeChange({ ...node.data, name, definition, explicit_state, implicit_state, properties, objects, actions, triggers });
    };

    const handleAIRequest = async (prompt) => {
        await handleLlmSubmit({
            llmPrompt: prompt,
            nodes: [node], // Context is mainly this node
            edges: [], // No edges context needed for internal node edits usually
            storyData: {},
            onSuccess: (newNodes, newEdges, msg) => {
                // expecting newNodes to contain the updated node
                const updated = newNodes.find(n => n.id === node.id);
                if (updated) {
                    const d = updated.data;
                    if (d.name) setName(d.name);
                    if (d.definition) setDefinition(d.definition);
                    if (d.explicit_state) setExplicitState(d.explicit_state);
                    if (d.implicit_state) setImplicitState(d.implicit_state);
                    if (d.properties) setProperties(d.properties);
                    if (d.objects) setObjects(d.objects);
                    if (d.actions) setActions(d.actions);
                    setTriggers(d.triggers || []);
                    // Trigger save
                    onNodeChange({ ...node.data, ...d });
                    setShowAI(false);
                }
            },
            onError: (err) => alert(t('panel.aiError', { error: err }))
        });
    };

    // Auto-save on blur or changes
    useEffect(() => {
        const timer = setTimeout(() => {
            const currentData = node.data || {};

            // Normalize for comparison (handle undefined vs empty array)
            const objectsChanged = JSON.stringify(objects || []) !== JSON.stringify(currentData.objects || []);
            const actionsChanged = JSON.stringify(actions || []) !== JSON.stringify(currentData.actions || []);
            const triggersChanged = JSON.stringify(triggers || []) !== JSON.stringify(currentData.triggers || []);
            const propertiesChanged = JSON.stringify(properties || {}) !== JSON.stringify(currentData.properties || {});
            // DSPP field checks
            const nameChanged = name !== (currentData.name || '');
            const definitionChanged = definition !== (currentData.definition || '');
            const explicitStateChanged = explicit_state !== (currentData.explicit_state || '');
            const implicitStateChanged = implicit_state !== (currentData.implicit_state || '');
            const idChanged = id !== (node.id || '');

            if (idChanged || nameChanged || definitionChanged || explicitStateChanged || implicitStateChanged || propertiesChanged || objectsChanged || actionsChanged || triggersChanged) {
                handleSave();
            }
        }, 800);
        return () => clearTimeout(timer);
    }, [id, name, definition, explicit_state, implicit_state, properties, objects, actions, triggers, node.id, node.data]);

    // ... (rest of methods)

    // Layout changes below


    const handleContainerClick = (e) => {
        // Only handle clicks if secondary editor is actually open
        if (!secondaryEditorOpen || !onSecondaryClose) {
            return;
        }

        // If clicking on a selected card or inside it, don't close
        if (e.target.closest('.card-item.selected')) {
            return;
        }

        // If clicking inside the secondary editor itself, don't close
        if (e.target.closest('.secondary-editor')) {
            return;
        }

        // If clicking inside AI assistant, don't close
        if (e.target.closest('.ai-assistant-panel')) return;

        // Otherwise, close the secondary editor
        onSecondaryClose();
    };

    const generateId = (prefix) => `${prefix}_${Date.now()}_${Math.random().toString(36).substr(2, 5)}`;

    const addObject = () => {
        const newObjects = [...objects, { id: generateId('obj'), name: t('object.newObject') }];
        setObjects(newObjects);
        onNodeChange({ ...node.data, name, definition, explicit_state, implicit_state, properties, objects: newObjects, actions, triggers });
    };

    const addAction = () => {
        const newActions = [...actions, { id: generateId('act'), text: t('action.singular'), effects: [] }];
        setActions(newActions);
        onNodeChange({ ...node.data, name, definition, explicit_state, implicit_state, properties, objects, actions: newActions, triggers });
    };

    const addTrigger = () => {
        const newTriggers = [...triggers, { id: generateId('trig'), type: 'post_enter', effects: [] }];
        setTriggers(newTriggers);
        onNodeChange({ ...node.data, name, definition, explicit_state, implicit_state, properties, objects, actions, triggers: newTriggers });
    };

    const [isAddingCharacter, setIsAddingCharacter] = useState(false);

    // Get characters currently located in this node
    const nodeCharacters = (availableCharacters || []).filter(c =>
        c.properties?.location === node.id
    );

    // Get characters available to add (not already in node)
    const availableToAdd = (availableCharacters || []).filter(c =>
        c.properties?.location !== node.id
    );

    const handleAddCharacter = (charId) => {
        if (!charId) return;

        const updatedChars = availableCharacters.map(c => {
            if (c.id === charId) {
                return {
                    ...c,
                    properties: {
                        ...(c.properties || {}),
                        location: node.id
                    }
                };
            }
            return c;
        });
        onUpdateCharacters(updatedChars);
        setIsAddingCharacter(false);
    };

    const handleRemoveCharacter = (charId, e) => {
        e.stopPropagation();
        if (confirm(t('node.removeCharacterConfirm'))) {
            const updatedChars = availableCharacters.map(c => {
                if (c.id === charId) {
                    return {
                        ...c,
                        properties: {
                            ...(c.properties || {}),
                            location: ''
                        }
                    };
                }
                return c;
            });
            onUpdateCharacters(updatedChars);
        }
    };

    return (
        <div
            className={`node-editor ${shifted ? 'shifted' : ''} ${selectedShape ? 'has-selection' : ''} ${node.type === 'generated' ? 'is-generate-node' : ''}`}
            onClick={handleContainerClick}
        >
            <div className="sticky-header">
                <h3>{name || node.id || t('node.unnamed')}</h3>
                <div style={{ display: 'flex', gap: '8px' }}>
                    <button
                        className="header-ai-btn"
                        onClick={() => setShowAI(!showAI)}
                        title={t('panel.aiAssist')}
                        style={{ color: 'var(--color-dark)' }}
                    >
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <path d="M12 2L14.5 9.5L22 12L14.5 14.5L12 22L9.5 14.5L2 12L9.5 9.5L12 2Z" fill="currentColor" />
                        </svg>
                        {t('panel.ai')}
                    </button>
                    <button className="header-close-btn" onClick={onNodeClose}>×</button>
                </div>
            </div>
            <AIAssistant
                isOpen={showAI}
                onClose={() => setShowAI(false)}
                onGenerate={handleAIRequest}
                contextInfo={t('node.aiContext')}
                title={t('node.aiTitle')}
            />
            <div className="editor-scroll-content">
                <div className="form-row two-col">
                    <div className="form-group">
                        <label>{t('node.id')}</label>
                        <input value={id} readOnly className="id-input" />
                    </div>
                    <div className="form-group">
                        <label>{t('node.name')}</label>
                        <input value={name} onChange={(e) => setName(e.target.value)} onBlur={handleSave} />
                    </div>
                </div>

                {/* DSPP Model Fields */}
                <div className="form-group">
                    <label>{t('node.definition')} <span className="field-hint">({t('node.definitionHint')})</span></label>
                    <textarea
                        className="notebook-textarea"
                        value={definition}
                        onChange={(e) => setDefinition(e.target.value)}
                        onBlur={handleSave}
                        rows={4}
                        placeholder={t('node.definitionPlaceholder')}
                    />
                </div>

                <div className="form-group">
                    <label>{t('node.explicitState')} <span className="field-hint">({t('node.explicitStateHint')})</span></label>
                    <textarea
                        className="notebook-textarea"
                        value={explicit_state}
                        onChange={(e) => setExplicitState(e.target.value)}
                        onBlur={handleSave}
                        rows={4}
                        placeholder={t('node.explicitStatePlaceholder')}
                    />
                </div>

                <div className="section collapsible-section">
                    <div 
                        className="section-header clickable"
                        onClick={() => setShowImplicitState(!showImplicitState)}
                    >
                        <h4>
                            <span className="collapse-indicator">{showImplicitState ? '▼' : '▶'}</span>
                            {t('node.implicitState')} <span className="field-hint">({t('node.implicitStateHint')})</span>
                        </h4>
                    </div>
                    {showImplicitState && (
                        <div className="form-group">
                            <textarea
                                className="notebook-textarea"
                                value={implicit_state}
                                onChange={(e) => setImplicitState(e.target.value)}
                                onBlur={handleSave}
                                rows={3}
                                placeholder={t('node.implicitStatePlaceholder')}
                            />
                        </div>
                    )}
                </div>

                <div className="section collapsible-section">
                    <div 
                        className="section-header clickable"
                        onClick={() => setShowProperties(!showProperties)}
                    >
                        <h4>
                            <span className="collapse-indicator">{showProperties ? '▼' : '▶'}</span>
                            {t('node.properties')} <span className="field-hint">({t('node.propertiesHint')})</span>
                        </h4>
                    </div>
                    {showProperties && (
                        <PropertiesEditor
                            properties={properties}
                            onChange={(newProps) => {
                                setProperties(newProps);
                                onNodeChange({ ...node.data, name, definition, explicit_state, implicit_state, properties: newProps, objects, actions, triggers });
                            }}
                        />
                    )}
                </div>

                <div className="section section-characters">
                    <div className="section-header">
                        <h4>{t('node.characters')}</h4>
                        <button
                            className="add-button"
                            onClick={() => setIsAddingCharacter(!isAddingCharacter)}
                            title={t('node.addCharacter')}
                        >+</button>
                    </div>

                    {isAddingCharacter && (
                        <div className="add-item-form">
                            <select
                                onChange={(e) => handleAddCharacter(e.target.value)}
                                defaultValue=""
                                autoFocus
                            >
                                <option value="" disabled>{t('node.selectCharacter')}</option>
                                {availableToAdd.map(c => (
                                    <option key={c.id} value={c.id}>{c.name || c.id}</option>
                                ))}
                                {availableToAdd.length === 0 && (
                                    <option disabled>{t('node.noAvailableCharacters')}</option>
                                )}
                            </select>
                        </div>
                    )}

                    <div className="card-list character-card-list">
                        {nodeCharacters.map((char, index) => (
                            <div
                                key={index}
                                className="card-item character-placement-card"
                                onClick={() => onEditCharacter && onEditCharacter(char.id)}
                                title={t('node.editCharacter')}
                            >
                                <div className="card-type-indicator type-character" style={{ background: '#9C27B0' }}></div>
                                <div className="card-content">
                                    <div className="char-name">{char.name || char.id}</div>
                                    <div className="placement-config">{t('node.locationAuthored')}</div>
                                </div>
                                <button
                                    className="card-delete-btn"
                                    onClick={(e) => handleRemoveCharacter(char.id, e)}
                                    title={t('node.removeFromNode')}
                                >×</button>
                            </div>
                        ))}
                        {nodeCharacters.length === 0 && <div className="empty-state">{t('node.noCharacters')}</div>}
                    </div>
                </div>

                <div className="section">
                    <div className="section-header">
                        <h4>{t('node.objects')}</h4>
                        <button className="add-button" onClick={addObject} title={t('node.addObject')}>+</button>
                    </div>
                    <div className="card-list">
                        {objects.map((obj, index) => (
                            <div
                                key={index}
                                className={`card-item ${selectedShape && selectedShape.type === 'object' && selectedShape.shape.id === obj.id ? 'selected' : ''}`}
                                onClick={() => onShapeClick(obj, 'object')}
                            >
                                <div className="card-type-indicator type-object"></div>
                                <div className="card-content">
                                    {obj.name || obj.id || t('node.objectItem', { index: index + 1 })}
                                </div>
                            </div>
                        ))}
                        {objects.length === 0 && <div className="empty-state">{t('node.noObjects')}</div>}
                    </div>
                </div>

                <div className="section">
                    <div className="section-header">
                        <h4>{t('node.actions')}</h4>
                        <button className="add-button" onClick={addAction} title={t('node.addAction')}>+</button>
                    </div>
                    <div className="card-list">
                        {actions.map((act, index) => (
                            <div
                                key={index}
                                className={`card-item ${selectedShape && selectedShape.type === 'action' && selectedShape.shape.id === act.id ? 'selected' : ''}`}
                                onClick={() => onShapeClick(act, 'action')}
                            >
                                <div className="card-type-indicator type-action"></div>
                                <div className="card-content">
                                    {act.name || act.text || act.id || t('node.actionItem', { index: index + 1 })}
                                </div>
                            </div>
                        ))}
                        {actions.length === 0 && <div className="empty-state">{t('node.noActions')}</div>}
                    </div>
                </div>

                <div className="section">
                    <div className="section-header">
                        <h4>{t('node.triggers')}</h4>
                        <button className="add-button" onClick={addTrigger} title={t('node.addTrigger')}>+</button>
                    </div>
                    <div className="card-list">
                        {triggers.map((trig, index) => (
                            <div
                                key={index}
                                className={`card-item ${selectedShape && selectedShape.type === 'trigger' && selectedShape.shape.id === trig.id ? 'selected' : ''}`}
                                onClick={() => onShapeClick(trig, 'trigger')}
                            >
                                <div className="card-type-indicator type-trigger"></div>
                                <div className="card-content">
                                    {trig.name || trig.type || trig.id || t('node.triggerItem', { index: index + 1 })}
                                </div>
                            </div>
                        ))}
                        {triggers.length === 0 && <div className="empty-state">{t('node.noTriggers')}</div>}
                    </div>
                </div>
            </div>
        </div>
    );
};

export default NodeEditor;