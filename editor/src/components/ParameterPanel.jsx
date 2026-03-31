import React, { useState, useMemo } from 'react';
import AIAssistant from './AIAssistant';
import { streamAIEdit, EDIT_MODES, AI_SOURCES } from '../services/aiService';
import './ParameterPanel.css';
import { useLocale } from '../i18n';

const isManagedSemanticParameter = (key) => key.startsWith('group_') || key.startsWith('tag_');

// Smart type detection
const detectValueType = (value) => {
    if (value === null || value === undefined) return 'string';
    if (typeof value === 'boolean') return 'boolean';
    if (typeof value === 'number') return 'number';
    if (Array.isArray(value)) return 'array';
    if (typeof value === 'object') return 'object';
    if (typeof value === 'string' && value.includes('\n')) return 'multiline';
    return 'string';
};

// Group parameters by prefix
const groupParameters = (parameters) => {
    const groups = {
        lorebook: { label: 'Lorebook', icon: '📚', keys: [], priority: 1 },
        flags: { label: 'Flags', icon: '🚩', keys: [], priority: 2 },
        stats: { label: 'Stats', icon: '📊', keys: [], priority: 3 },
        config: { label: 'Config', icon: '⚙️', keys: [], priority: 4 },
        other: { label: 'Other', icon: '📦', keys: [], priority: 5 }
    };

    Object.entries(parameters).forEach(([key, value]) => {
        const type = detectValueType(value);
        
        // Lorebook: lore_* prefix or multiline strings
        if (key.startsWith('lore_') || key.startsWith('lorebook_') || 
            (type === 'multiline' && (key.includes('style') || key.includes('world') || key.includes('npc') || key.includes('protagonist')))) {
            groups.lorebook.keys.push(key);
        }
        // Flags: boolean values or *_available, *_examined, *_found, *_discovered patterns
        else if (type === 'boolean' || 
                 key.endsWith('_available') || key.endsWith('_examined') || 
                 key.endsWith('_found') || key.endsWith('_discovered') ||
                 key.endsWith('_noticed') || key.endsWith('_warned') ||
                 key.startsWith('has_') || key.startsWith('is_') ||
                 key.startsWith('saw_') || key.startsWith('heard_') ||
                 key.startsWith('met_') || key.startsWith('learned_')) {
            groups.flags.keys.push(key);
        }
        // Stats: numeric values
        else if (type === 'number') {
            groups.stats.keys.push(key);
        }
        // Config: arrays or objects
        else if (type === 'array' || type === 'object') {
            groups.config.keys.push(key);
        }
        // Other: everything else
        else {
            groups.other.keys.push(key);
        }
    });

    // Filter out empty groups and sort by priority
    return Object.entries(groups)
        .filter(([_, group]) => group.keys.length > 0)
        .sort((a, b) => a[1].priority - b[1].priority)
        .map(([id, group]) => ({ id, ...group }));
};

// Preview text for long content
const getPreviewText = (value, maxLines = 3) => {
    if (typeof value !== 'string') return '';
    const lines = value.split('\n').filter(line => line.trim());
    if (lines.length <= maxLines) return value;
    return lines.slice(0, maxLines).join('\n') + '\n...';
};

const ParameterPanel = ({ isOpen, onClose, parameters = {}, onUpdateParameters, storyData }) => {
    const [editingKey, setEditingKey] = useState(null);
    const [newKeyName, setNewKeyName] = useState('');
    const [showAI, setShowAI] = useState(false);
    const [aiThinking, setAiThinking] = useState(false);
    const [aiMessage, setAiMessage] = useState('');
    const [searchTerm, setSearchTerm] = useState('');
    const [collapsedGroups, setCollapsedGroups] = useState({});
    const [expandedCards, setExpandedCards] = useState({});
    const [typeFilter, setTypeFilter] = useState('all');
    const { t } = useLocale();

    if (!isOpen) return null;

    // Filter parameters by search term
    const filteredParameters = useMemo(() => {
        if (!searchTerm && typeFilter === 'all') return parameters;
        
        return Object.fromEntries(
            Object.entries(parameters).filter(([key, value]) => {
                if (isManagedSemanticParameter(key)) {
                    return false;
                }
                const matchesSearch = !searchTerm || 
                    key.toLowerCase().includes(searchTerm.toLowerCase()) ||
                    String(value).toLowerCase().includes(searchTerm.toLowerCase());
                
                const type = detectValueType(value);
                const matchesType = typeFilter === 'all' || 
                    (typeFilter === 'text' && (type === 'string' || type === 'multiline')) ||
                    (typeFilter === 'number' && type === 'number') ||
                    (typeFilter === 'boolean' && type === 'boolean') ||
                    (typeFilter === 'complex' && (type === 'array' || type === 'object'));
                
                return matchesSearch && matchesType;
            })
        );
    }, [parameters, searchTerm, typeFilter]);

    const groups = useMemo(() => groupParameters(filteredParameters), [filteredParameters]);

    const handleAIRequest = async (prompt) => {
        setAiThinking(true);
        setAiMessage('Starting...');
        
        let setCount = 0;
        let deletedCount = 0;
        let currentParams = { ...parameters };

        await streamAIEdit({
            prompt,
            mode: EDIT_MODES.PARAMETERS,
            parameters: parameters,
            storyData: storyData,
            source: AI_SOURCES.PARAMETER_PANEL,

            onThinking: (message) => {
                setAiMessage(message);
            },

            onFunctionCall: (functionName, args) => {
                setAiMessage(`Calling ${functionName}...`);
            },

            onParameterSet: (key, value, isNew) => {
                setCount++;
                currentParams = { ...currentParams, [key]: value };
                onUpdateParameters(currentParams);
            },

            onParameterDeleted: (key) => {
                deletedCount++;
                const newParams = { ...currentParams };
                delete newParams[key];
                currentParams = newParams;
                onUpdateParameters(currentParams);
            },

            onComplete: ({ message, summary }) => {
                setAiThinking(false);
                setAiMessage('');
                setShowAI(false);
                
                const summaryText = [
                    setCount > 0 ? t('panel.summarySet', { count: setCount }) : null,
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

    const handleValueChange = (key, newValue, type) => {
        let parsedValue = newValue;
        if (type === 'number') {
            parsedValue = parseFloat(newValue) || 0;
        } else if (type === 'boolean') {
            parsedValue = newValue;
        }
        onUpdateParameters({
            ...parameters,
            [key]: parsedValue
        });
    };

    const handleKeyRename = (oldKey, newKey) => {
        if (newKey && newKey !== oldKey && !parameters.hasOwnProperty(newKey)) {
            const newParams = { ...parameters };
            newParams[newKey] = newParams[oldKey];
            delete newParams[oldKey];
            onUpdateParameters(newParams);
        }
        setEditingKey(null);
        setNewKeyName('');
    };

    const handleAddParameter = (type = 'string') => {
        const baseKey = 'new_parameter';
        let key = baseKey;
        let counter = 1;
        while (parameters.hasOwnProperty(key)) {
            key = `${baseKey}_${counter}`;
            counter++;
        }
        
        let defaultValue = '';
        if (type === 'number') defaultValue = 0;
        if (type === 'boolean') defaultValue = false;
        if (type === 'multiline') defaultValue = '';
        if (type === 'array') defaultValue = [];
        if (type === 'object') defaultValue = {};
        
        onUpdateParameters({
            ...parameters,
            [key]: defaultValue
        });
    };

    const handleDeleteParameter = (key) => {
        const newParams = { ...parameters };
        delete newParams[key];
        onUpdateParameters(newParams);
    };

    const handleDuplicateParameter = (key) => {
        let newKey = `${key}_copy`;
        let counter = 1;
        while (parameters.hasOwnProperty(newKey)) {
            newKey = `${key}_copy_${counter}`;
            counter++;
        }
        onUpdateParameters({
            ...parameters,
            [newKey]: JSON.parse(JSON.stringify(parameters[key]))
        });
    };

    const toggleGroup = (groupId) => {
        setCollapsedGroups(prev => ({
            ...prev,
            [groupId]: !prev[groupId]
        }));
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
                                rows={Math.min(20, Math.max(6, value.split('\n').length + 2))}
                            />
                        </div>
                    )}
                </div>
            );
        }

        if (type === 'array') {
            return (
                <div className="array-editor">
                    <div className="array-items">
                        {value.map((item, index) => (
                            <div key={index} className="array-item">
                                <input
                                    type="text"
                                    value={typeof item === 'object' ? JSON.stringify(item) : item}
                                    onChange={(e) => {
                                        const newArray = [...value];
                                        try {
                                            newArray[index] = JSON.parse(e.target.value);
                                        } catch {
                                            newArray[index] = e.target.value;
                                        }
                                        handleValueChange(key, newArray, type);
                                    }}
                                    className="param-input"
                                />
                                <button 
                                    className="array-remove-btn"
                                    onClick={() => {
                                        const newArray = value.filter((_, i) => i !== index);
                                        handleValueChange(key, newArray, type);
                                    }}
                                >×</button>
                            </div>
                        ))}
                    </div>
                    <button 
                        className="array-add-btn"
                        onClick={() => handleValueChange(key, [...value, ''], type)}
                    >+ Add Item</button>
                </div>
            );
        }

        if (type === 'object') {
            return (
                <div className={`object-editor ${isExpanded ? 'expanded' : ''}`}>
                    {!isExpanded ? (
                        <div className="preview-container" onClick={() => toggleCardExpand(key)}>
                            <code className="preview-text">{JSON.stringify(value, null, 2).slice(0, 100)}...</code>
                            <button className="expand-btn">
                                {t('parameter.expandKeys', { count: Object.keys(value).length })}
                            </button>
                        </div>
                    ) : (
                        <div className="expanded-editor">
                            <div className="editor-toolbar">
                                <span className="line-count">{t('parameter.keys', { count: Object.keys(value).length })}</span>
                                <button className="collapse-btn" onClick={() => toggleCardExpand(key)}>
                                    {t('parameter.collapse')}
                                </button>
                            </div>
                            <textarea
                                value={JSON.stringify(value, null, 2)}
                                onChange={(e) => {
                                    try {
                                        const parsed = JSON.parse(e.target.value);
                                        handleValueChange(key, parsed, type);
                                    } catch {
                                        // Invalid JSON, don't update
                                    }
                                }}
                                className="param-textarea json"
                                rows={Math.min(15, Object.keys(value).length * 2 + 4)}
                            />
                        </div>
                    )}
                </div>
            );
        }

        // Default: simple string
        return (
            <input
                type="text"
                value={value}
                onChange={(e) => handleValueChange(key, e.target.value, type)}
                className="param-input"
            />
        );
    };

    const renderParameterCard = (key, value) => {
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
                                    if (e.key === 'Escape') { setEditingKey(null); setNewKeyName(''); }
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
                            onClick={() => handleDuplicateParameter(key)}
                            title={t('parameter.duplicate')}
                        >⧉</button>
                        <button
                            className="param-action-btn delete"
                            onClick={() => handleDeleteParameter(key)}
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

    const renderGroup = (group) => {
        const isCollapsed = collapsedGroups[group.id];
        const groupParams = group.keys.map(key => [key, filteredParameters[key]]);

        return (
            <div key={group.id} className={`param-group ${isCollapsed ? 'collapsed' : ''}`}>
                <div className="group-header" onClick={() => toggleGroup(group.id)}>
                    <span className="group-icon">{group.icon}</span>
                    <span className="group-label">{t(`parameter.group.${group.id}`)}</span>
                    <span className="group-count">{group.keys.length}</span>
                    <span className="group-toggle">{isCollapsed ? '▶' : '▼'}</span>
                </div>
                {!isCollapsed && (
                    <div className="group-content">
                        {groupParams.map(([key, value]) => renderParameterCard(key, value))}
                    </div>
                )}
            </div>
        );
    };

    return (
        <div className="parameter-panel right-panel refined">
            <div className="panel-header">
                <h3>{t('panel.parameters')}</h3>
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
                contextInfo={t('panel.manageGlobalParameters')}
                title={t('panel.paramAiTitle')}
                externalLoading={aiThinking}
                externalMessage={aiMessage}
            />

            {/* Search and Filter Bar */}
            <div className="param-toolbar">
                <div className="search-container">
                    <input
                        type="text"
                        placeholder={t('panel.searchParameters')}
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        className="search-input"
                    />
                    {searchTerm && (
                        <button className="clear-search" onClick={() => setSearchTerm('')}>×</button>
                    )}
                </div>
                <div className="filter-container">
                    <select 
                        value={typeFilter} 
                        onChange={(e) => setTypeFilter(e.target.value)}
                        className="type-filter"
                    >
                        <option value="all">{t('parameter.allTypes')}</option>
                        <option value="text">{t('parameter.text')}</option>
                        <option value="number">{t('parameter.number')}</option>
                        <option value="boolean">{t('parameter.boolean')}</option>
                        <option value="complex">{t('parameter.complex')}</option>
                    </select>
                </div>
            </div>

            {/* Parameter Groups */}
            <div className="param-content">
                {groups.length === 0 ? (
                    <div className="empty-state">
                        {Object.keys(parameters).length === 0 
                            ? t('panel.noParameters')
                            : t('panel.noParametersSearch')}
                    </div>
                ) : (
                    groups.map(group => renderGroup(group))
                )}
            </div>

            {/* Add Parameter Footer */}
            <div className="param-footer">
                <div className="add-dropdown">
                    <button className="add-param-btn">{t('panel.addParameter')}</button>
                    <div className="add-menu">
                        <button onClick={() => handleAddParameter('string')}>{t('parameter.type.string')}</button>
                        <button onClick={() => handleAddParameter('number')}>{t('parameter.type.number')}</button>
                        <button onClick={() => handleAddParameter('boolean')}>{t('parameter.type.boolean')}</button>
                        <button onClick={() => handleAddParameter('multiline')}>{t('parameter.type.multiline')}</button>
                        <button onClick={() => handleAddParameter('array')}>{t('parameter.type.array')}</button>
                        <button onClick={() => handleAddParameter('object')}>{t('parameter.type.object')}</button>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default ParameterPanel;
