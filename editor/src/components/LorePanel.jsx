import React, { useMemo, useState } from 'react';
import AIAssistant from './AIAssistant';
import { streamAIEdit, EDIT_MODES, AI_SOURCES } from '../services/aiService';
import './ParameterPanel.css';
import { useLocale } from '../i18n';

const isLoreKey = (key) => key.startsWith('lore_') || key.startsWith('lorebook_');

const detectValueType = (value) => {
    if (value === null || value === undefined) return 'string';
    if (typeof value === 'boolean') return 'boolean';
    if (typeof value === 'number') return 'number';
    if (Array.isArray(value)) return 'array';
    if (typeof value === 'object') return 'object';
    if (typeof value === 'string' && value.includes('\n')) return 'multiline';
    return 'string';
};

const getPreviewText = (value, maxLines = 4) => {
    if (typeof value !== 'string') return '';
    const lines = value.split('\n').filter(line => line.trim());
    if (lines.length <= maxLines) return value;
    return lines.slice(0, maxLines).join('\n') + '\n...';
};

const normalizeLoreKey = (key) => {
    const trimmed = (key || '').trim();
    if (!trimmed) return '';
    if (isLoreKey(trimmed)) return trimmed;
    return `lore_${trimmed}`;
};

const LORE_TEMPLATES = {
    custom: { key: 'lore_new_entry', value: '' },
    world: { key: 'lore_world', value: '' },
    writingStyle: { key: 'lore_writing_style', value: '' },
    protagonist: { key: 'lore_protagonist', value: '' },
    npcGuidelines: { key: 'lore_npc_guidelines', value: '' }
};

const LorePanel = ({ isOpen, onClose, parameters = {}, onUpdateParameters, storyData }) => {
    const [editingKey, setEditingKey] = useState(null);
    const [newKeyName, setNewKeyName] = useState('');
    const [showAI, setShowAI] = useState(false);
    const [aiThinking, setAiThinking] = useState(false);
    const [aiMessage, setAiMessage] = useState('');
    const [searchTerm, setSearchTerm] = useState('');
    const [expandedCards, setExpandedCards] = useState({});
    const { t } = useLocale();

    if (!isOpen) return null;

    const loreParameters = useMemo(() => {
        return Object.fromEntries(
            Object.entries(parameters).filter(([key, value]) => {
                if (!isLoreKey(key)) return false;
                if (!searchTerm) return true;
                const haystack = `${key}\n${typeof value === 'string' ? value : JSON.stringify(value)}`.toLowerCase();
                return haystack.includes(searchTerm.toLowerCase());
            })
        );
    }, [parameters, searchTerm]);

    const handleAIRequest = async (prompt) => {
        setAiThinking(true);
        setAiMessage('Starting...');

        let setCount = 0;
        let deletedCount = 0;
        let currentParams = { ...parameters };

        await streamAIEdit({
            prompt: `${prompt}\n\nFocus on lore entries only. Use lore_ keys for long-form world, style, character, or rules guidance.`,
            mode: EDIT_MODES.PARAMETERS,
            parameters,
            storyData,
            source: AI_SOURCES.LORE_PANEL,
            onThinking: (message) => setAiMessage(message),
            onFunctionCall: (functionName) => setAiMessage(`Calling ${functionName}...`),
            onParameterSet: (key, value) => {
                setCount++;
                currentParams = { ...currentParams, [key]: value };
                onUpdateParameters(currentParams);
            },
            onParameterDeleted: (key) => {
                deletedCount++;
                const nextParams = { ...currentParams };
                delete nextParams[key];
                currentParams = nextParams;
                onUpdateParameters(currentParams);
            },
            onComplete: ({ message }) => {
                setAiThinking(false);
                setAiMessage('');
                setShowAI(false);
                const summaryText = [
                    setCount > 0 ? t('panel.summarySet', { count: setCount }) : null,
                    deletedCount > 0 ? t('panel.summaryDeleted', { count: deletedCount }) : null
                ].filter(Boolean).join(', ');
                alert(summaryText ? t('panel.aiComplete', { summary: summaryText }) : (message || t('panel.aiCompleteNoChanges')));
            },
            onError: (error) => {
                setAiThinking(false);
                setAiMessage('');
                alert(t('panel.aiError', { error }));
            }
        });
    };

    const handleValueChange = (key, newValue, type) => {
        let parsedValue = newValue;
        if (type === 'number') {
            parsedValue = parseFloat(newValue) || 0;
        }
        onUpdateParameters({
            ...parameters,
            [key]: parsedValue
        });
    };

    const handleKeyRename = (oldKey, newKey) => {
        const normalizedKey = normalizeLoreKey(newKey);
        if (normalizedKey && normalizedKey !== oldKey && !parameters.hasOwnProperty(normalizedKey)) {
            const nextParams = { ...parameters };
            nextParams[normalizedKey] = nextParams[oldKey];
            delete nextParams[oldKey];
            onUpdateParameters(nextParams);
        }
        setEditingKey(null);
        setNewKeyName('');
    };

    const createUniqueLoreKey = (baseKey) => {
        let key = baseKey;
        let counter = 1;
        while (parameters.hasOwnProperty(key)) {
            key = `${baseKey}_${counter}`;
            counter++;
        }
        return key;
    };

    const handleAddLoreEntry = (templateId = 'custom') => {
        const template = LORE_TEMPLATES[templateId] || LORE_TEMPLATES.custom;
        const key = createUniqueLoreKey(template.key);
        onUpdateParameters({
            ...parameters,
            [key]: template.value
        });
        setEditingKey(key);
        setNewKeyName(key);
    };

    const handleDeleteEntry = (key) => {
        const nextParams = { ...parameters };
        delete nextParams[key];
        onUpdateParameters(nextParams);
    };

    const handleDuplicateEntry = (key) => {
        const newKey = createUniqueLoreKey(`${key}_copy`);
        onUpdateParameters({
            ...parameters,
            [newKey]: JSON.parse(JSON.stringify(parameters[key]))
        });
    };

    const toggleCardExpand = (key) => {
        setExpandedCards(prev => ({
            ...prev,
            [key]: !prev[key]
        }));
    };

    const renderValueEditor = (key, value, type) => {
        const isExpanded = expandedCards[key];

        if (type === 'boolean') {
            return (
                <label className="param-toggle">
                    <input
                        type="checkbox"
                        checked={value}
                        onChange={(e) => handleValueChange(key, e.target.checked, type)}
                    />
                    <span className="toggle-slider"></span>
                    <span className="toggle-label">{value ? 'true' : 'false'}</span>
                </label>
            );
        }

        if (type === 'number') {
            return (
                <input
                    type="number"
                    value={value}
                    onChange={(e) => handleValueChange(key, e.target.value, type)}
                    className="param-input number"
                />
            );
        }

        if (type === 'multiline') {
            return (
                <div className={`multiline-editor ${isExpanded ? 'expanded' : ''}`}>
                    {!isExpanded ? (
                        <div className="preview-container" onClick={() => toggleCardExpand(key)}>
                            <pre className="preview-text">{getPreviewText(value)}</pre>
                            <button className="expand-btn">
                                {t('parameter.expandLines', { count: value.split('\n').length })}
                            </button>
                        </div>
                    ) : (
                        <div className="expanded-editor">
                            <div className="editor-toolbar">
                                <span className="line-count">{t('parameter.lines', { count: value.split('\n').length })}</span>
                                <button className="collapse-btn" onClick={() => toggleCardExpand(key)}>
                                    {t('parameter.collapse')}
                                </button>
                            </div>
                            <textarea
                                value={value}
                                onChange={(e) => handleValueChange(key, e.target.value, type)}
                                className="param-textarea"
                                rows={Math.min(20, Math.max(8, value.split('\n').length + 2))}
                            />
                        </div>
                    )}
                </div>
            );
        }

        if (type === 'array' || type === 'object') {
            const objectValue = type === 'array' ? value : value || {};
            const preview = JSON.stringify(objectValue, null, 2);
            const size = type === 'array' ? objectValue.length : Object.keys(objectValue).length;
            return (
                <div className={`object-editor ${isExpanded ? 'expanded' : ''}`}>
                    {!isExpanded ? (
                        <div className="preview-container" onClick={() => toggleCardExpand(key)}>
                            <code className="preview-text">{preview.slice(0, 140)}...</code>
                            <button className="expand-btn">
                                {type === 'array'
                                    ? t('parameter.expandItems', { count: size })
                                    : t('parameter.expandKeys', { count: size })}
                            </button>
                        </div>
                    ) : (
                        <div className="expanded-editor">
                            <div className="editor-toolbar">
                                <span className="line-count">{type === 'array' ? t('parameter.items', { count: size }) : t('parameter.keys', { count: size })}</span>
                                <button className="collapse-btn" onClick={() => toggleCardExpand(key)}>
                                    {t('parameter.collapse')}
                                </button>
                            </div>
                            <textarea
                                value={preview}
                                onChange={(e) => {
                                    try {
                                        const parsed = JSON.parse(e.target.value);
                                        handleValueChange(key, parsed, type);
                                    } catch {
                                        // Ignore invalid JSON while typing.
                                    }
                                }}
                                className="param-textarea json"
                                rows={Math.min(16, Math.max(8, preview.split('\n').length))}
                            />
                        </div>
                    )}
                </div>
            );
        }

        return (
            <input
                type="text"
                value={value}
                onChange={(e) => handleValueChange(key, e.target.value, type)}
                className="param-input"
            />
        );
    };

    const renderLoreCard = (key, value) => {
        const type = detectValueType(value);
        const isLongContent = type === 'multiline' || type === 'array' || type === 'object';

        return (
            <div key={key} className={`param-card ${type} ${isLongContent ? 'long-content' : ''}`}>
                <div className="param-card-header">
                    <div className="param-key-container">
                        {editingKey === key ? (
                            <input
                                type="text"
                                value={newKeyName}
                                onChange={(e) => setNewKeyName(e.target.value)}
                                onBlur={() => handleKeyRename(key, newKeyName)}
                                onKeyDown={(e) => {
                                    if (e.key === 'Enter') handleKeyRename(key, newKeyName);
                                    if (e.key === 'Escape') {
                                        setEditingKey(null);
                                        setNewKeyName('');
                                    }
                                }}
                                autoFocus
                                className="param-key-input"
                            />
                        ) : (
                            <span
                                className="param-key"
                                onClick={() => { setEditingKey(key); setNewKeyName(key); }}
                                title={t('parameter.rename')}
                            >
                                {key}
                            </span>
                        )}
                        <span className={`type-badge ${type}`}>{t(`parameter.type.${type}`)}</span>
                    </div>
                    <div className="param-actions">
                        <button
                            className="param-action-btn duplicate"
                            onClick={() => handleDuplicateEntry(key)}
                            title={t('parameter.duplicate')}
                        >⧉</button>
                        <button
                            className="param-action-btn delete"
                            onClick={() => handleDeleteEntry(key)}
                            title={t('parameter.delete')}
                        >×</button>
                    </div>
                </div>
                <div className="param-card-body">
                    {renderValueEditor(key, value, type)}
                </div>
            </div>
        );
    };

    return (
        <div className="parameter-panel right-panel refined lore-panel">
            <div className="panel-header">
                <h3>{t('panel.lore')}</h3>
                <div className="header-buttons-group">
                    <button
                        className="header-ai-btn"
                        onClick={() => setShowAI(!showAI)}
                        title={t('panel.aiAssist')}
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
                contextInfo={t('panel.manageLoreEntries')}
                title={t('panel.loreAiTitle')}
                externalLoading={aiThinking}
                externalMessage={aiMessage}
            />

            <div className="param-toolbar">
                <div className="search-container">
                    <input
                        type="text"
                        placeholder={t('panel.searchLore')}
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        className="search-input"
                    />
                    {searchTerm && (
                        <button className="clear-search" onClick={() => setSearchTerm('')}>×</button>
                    )}
                </div>
            </div>

            <div className="param-content">
                <div className="info-box" style={{
                    padding: '12px 14px',
                    background: 'var(--color-surface-alt, #f8f9fa)',
                    border: '1px solid var(--color-border)',
                    marginBottom: 12
                }}>
                    {t('lore.info')}
                </div>
                {Object.keys(loreParameters).length === 0 ? (
                    <div className="empty-state">
                        {searchTerm ? t('lore.emptySearch') : t('lore.empty')}
                    </div>
                ) : (
                    Object.entries(loreParameters).map(([key, value]) => renderLoreCard(key, value))
                )}
            </div>

            <div className="param-footer">
                <div className="add-dropdown">
                    <button className="add-param-btn">{t('panel.addLore')}</button>
                    <div className="add-menu">
                        <button onClick={() => handleAddLoreEntry('custom')}>{t('lore.customEntry')}</button>
                        <button onClick={() => handleAddLoreEntry('world')}>{t('lore.world')}</button>
                        <button onClick={() => handleAddLoreEntry('writingStyle')}>{t('lore.writingStyle')}</button>
                        <button onClick={() => handleAddLoreEntry('protagonist')}>{t('lore.protagonist')}</button>
                        <button onClick={() => handleAddLoreEntry('npcGuidelines')}>{t('lore.npcGuidelines')}</button>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default LorePanel;
