import React, { useState, useEffect } from 'react';
import AIAssistant from './AIAssistant';
import PropertiesEditor from './PropertiesEditor';
import MemoryEditor from './MemoryEditor';
import { streamAIEdit, EDIT_MODES, AI_SOURCES } from '../services/aiService';
import { useLocale } from '../i18n';

const CharacterPanel = ({ isOpen, onClose, characters, onUpdateCharacters, nodes, initialCharId, storyData }) => {
    const [selectedCharId, setSelectedCharId] = useState(null);
    const [isEditingChar, setIsEditingChar] = useState(false);
    const [showAI, setShowAI] = useState(false);
    const [aiThinking, setAiThinking] = useState(false);
    const [aiMessage, setAiMessage] = useState('');
    const { t } = useLocale();
    useEffect(() => {
        if (isOpen && initialCharId) {
            const charExists = characters.some(c => c.id === initialCharId);
            if (charExists) {
                setSelectedCharId(initialCharId);
                setIsEditingChar(true);
            }
        }
    }, [isOpen, initialCharId, characters]);

    useEffect(() => {
        if (!isOpen) {
            setSelectedCharId(null);
            setIsEditingChar(false);
            setShowAI(false);
        }
    }, [isOpen]);

    const handleAIRequest = async (prompt) => {
        setAiThinking(true);
        setAiMessage('Starting...');
        
        let addedCount = 0;
        let updatedCount = 0;
        let deletedCount = 0;
        let currentCharacters = [...characters];

        await streamAIEdit({
            prompt,
            mode: EDIT_MODES.CHARACTERS,
            characters: characters,
            storyData: storyData,
            source: AI_SOURCES.CHARACTER_PANEL,

            onThinking: (message) => setAiMessage(message),
            onFunctionCall: (functionName) => setAiMessage(`Calling ${functionName}...`),

            onCharacterCreated: (character) => {
                addedCount++;
                currentCharacters = [...currentCharacters, character];
                onUpdateCharacters(currentCharacters);
            },
            onCharacterUpdated: (character) => {
                updatedCount++;
                currentCharacters = currentCharacters.map(c =>
                    c.id === character.id ? { ...c, ...character } : c
                );
                onUpdateCharacters(currentCharacters);
            },
            onCharacterDeleted: (characterId) => {
                deletedCount++;
                currentCharacters = currentCharacters.filter(c => c.id !== characterId);
                onUpdateCharacters(currentCharacters);
            },

            onComplete: ({ message }) => {
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

    const selectedChar = characters.find(c => c.id === selectedCharId);

    const availableNodes = Object.entries(nodes || {}).map(([id, node]) => ({
        id,
        name: node.name || id
    }));

    const handleCardClick = (charId) => {
        setSelectedCharId(charId);
        setIsEditingChar(true);
    };

    const handleBackToList = () => {
        setIsEditingChar(false);
        setSelectedCharId(null);
        setIsAddingPlacement(false);
    };

    const handleAddCharacter = () => {
        const newChar = {
            id: `char_${Date.now()}`,
            name: t('character.newCharacter'),
            definition: '',
            explicit_state: '',
            implicit_state: '',
            memory: [],
            properties: {},
            is_playable: false,
            is_hittable: false
        };
        onUpdateCharacters([...characters, newChar]);
        setSelectedCharId(newChar.id);
        setIsEditingChar(true);
    };

    const handleDeleteCharacter = (id, e) => {
        e.stopPropagation();
        if (window.confirm(t('character.deleteConfirm'))) {
            onUpdateCharacters(characters.filter(c => c.id !== id));
            if (selectedCharId === id) {
                setSelectedCharId(null);
                setIsEditingChar(false);
            }
        }
    };

    const updateSelectedChar = (updates) => {
        onUpdateCharacters(characters.map(c => c.id === selectedCharId ? { ...c, ...updates } : c));
    };

    const handleLocationChange = (nodeId) => {
        if (!selectedChar) return;
        updateSelectedChar({
            properties: {
                ...(selectedChar.properties || {}),
                location: nodeId || ''
            }
        });
    };

    // Collapsible section state
    const [showImplicitState, setShowImplicitState] = useState(false);
    const [showMemory, setShowMemory] = useState(false);
    const [showProperties, setShowProperties] = useState(false);

    return (
        <div className={`character-panel right-panel ${isEditingChar ? 'editing' : ''}`}>
            {/* Character List View */}
            <div className={`char-list-view ${isEditingChar ? 'hidden' : ''}`}>
                <div className="panel-header">
                    <h3>{t('panel.characters')}</h3>
                    <div className="header-buttons-group">
                        <button
                            className="header-ai-btn"
                            onClick={() => setShowAI(!showAI)}
                            title={t('panel.aiAssist')}
                            style={{ color: '#9C27B0' }}
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
                    isOpen={showAI && !isEditingChar}
                    onClose={() => !aiThinking && setShowAI(false)}
                    onGenerate={handleAIRequest}
                    contextInfo={t('panel.manageCharacterList')}
                    title={t('panel.characterAiTitle')}
                    externalLoading={aiThinking}
                    externalMessage={aiMessage}
                />

                <div className="char-cards-container">
                    <button className="add-char-card" onClick={handleAddCharacter}>
                        <div className="add-icon">+</div>
                        <div className="add-text">{t('character.newCharacter')}</div>
                    </button>

                    {characters.map(char => (
                        <div
                            key={char.id}
                            className="char-card"
                            onClick={() => handleCardClick(char.id)}
                        >
                            <div className="char-card-header">
                                <h4>{char.name}</h4>
                                <button
                                    className="char-card-delete"
                                    onClick={(e) => handleDeleteCharacter(char.id, e)}
                                >×</button>
                            </div>
                            <div className="char-card-description">
                                {char.definition ? char.definition.substring(0, 80) + (char.definition.length > 80 ? '...' : '') : t('character.noDefinition')}
                            </div>
                            <div className="char-card-badges">
                                {char.is_playable && <span className="badge playable">{t('character.playable')}</span>}
                                {char.is_hittable && <span className="badge combat">{t('character.combat')}</span>}
                                {char.properties?.location && (
                                    <span className="badge placement" title={char.properties.location}>
                                        {nodes?.[char.properties.location]?.name || char.properties.location}
                                    </span>
                                )}
                            </div>
                        </div>
                    ))}

                    {characters.length === 0 && (
                        <div className="empty-message">
                            {t('character.empty')}
                        </div>
                    )}
                </div>
            </div>

            {/* Character Editor View */}
            {isEditingChar && selectedChar && (
                <div className="char-editor-view">
                    <div className="panel-header">
                        <button className="back-btn" onClick={handleBackToList}>{t('character.back')}</button>
                        <h3 style={{ margin: '0 8px', flex: 1, textAlign: 'center' }}>{selectedChar.name || t('character.editTitle')}</h3>
                        <div className="header-buttons-group">
                            <button
                                className="header-ai-btn"
                                onClick={() => setShowAI(!showAI)}
                                title={t('panel.aiAssist')}
                                style={{ color: '#9C27B0' }}
                            >
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                                    <path d="M12 2L14.5 9.5L22 12L14.5 14.5L12 22L9.5 14.5L2 12L9.5 9.5L12 2Z" fill="currentColor" />
                                </svg>
                                {t('panel.ai')}
                            </button>
                            <button className="close-btn" onClick={onClose}>×</button>
                        </div>
                    </div>

                    <div className="char-editor-content">
                        {/* ID + Name */}
                        <div className="form-group">
                            <div className="char-inline-input-group">
                                <label className="char-input-label">{t('node.id')}:</label>
                                <input
                                    className="char-input-field"
                                    value={selectedChar.id}
                                    onChange={(e) => updateSelectedChar({ id: e.target.value })}
                                />
                            </div>
                            <div className="char-inline-input-group">
                                <label className="char-input-label">{t('node.name')}:</label>
                                <input
                                    className="char-input-field"
                                    value={selectedChar.name}
                                    onChange={(e) => updateSelectedChar({ name: e.target.value })}
                                    placeholder={t('character.namePlaceholder')}
                                />
                            </div>
                        </div>

                        {/* DSPP Fields */}
                        <div className="form-group">
                            <label>{t('node.definition')} <span className="field-hint">({t('character.definitionHint')})</span></label>
                            <textarea
                                className="notebook-textarea"
                                value={selectedChar.definition || ''}
                                onChange={(e) => updateSelectedChar({ definition: e.target.value })}
                                rows={4}
                                placeholder={t('character.definitionPlaceholder')}
                            />
                        </div>

                        <div className="form-group">
                            <label>{t('node.explicitState')} <span className="field-hint">({t('character.explicitStateHint')})</span></label>
                            <textarea
                                className="notebook-textarea"
                                value={selectedChar.explicit_state || ''}
                                onChange={(e) => updateSelectedChar({ explicit_state: e.target.value })}
                                rows={2}
                                placeholder={t('character.explicitStatePlaceholder')}
                            />
                        </div>

                        <div className="section collapsible-section">
                            <div
                                className="section-header clickable"
                                onClick={() => setShowImplicitState(!showImplicitState)}
                            >
                                <h4>
                                    <span className="collapse-indicator">{showImplicitState ? '▼' : '▶'}</span>
                                    {t('character.implicitState')} <span className="field-hint">({t('character.implicitHint')})</span>
                                </h4>
                            </div>
                            {showImplicitState && (
                                <div className="form-group">
                                    <textarea
                                        className="notebook-textarea"
                                        value={selectedChar.implicit_state || ''}
                                        onChange={(e) => updateSelectedChar({ implicit_state: e.target.value })}
                                        rows={2}
                                        placeholder={t('character.implicitPlaceholder')}
                                    />
                                </div>
                            )}
                        </div>

                        <div className="section collapsible-section">
                            <div
                                className="section-header clickable"
                                onClick={() => setShowMemory(!showMemory)}
                            >
                                <h4>
                                    <span className="collapse-indicator">{showMemory ? '▼' : '▶'}</span>
                                    {t('character.memory')} <span className="field-hint">({t('character.memoryHint')})</span>
                                </h4>
                            </div>
                            {showMemory && (
                                <MemoryEditor
                                    memory={selectedChar.memory || []}
                                    onChange={(newMemory) => updateSelectedChar({ memory: newMemory })}
                                />
                            )}
                        </div>

                        <div className="section collapsible-section">
                            <div
                                className="section-header clickable"
                                onClick={() => setShowProperties(!showProperties)}
                            >
                                <h4>
                                    <span className="collapse-indicator">{showProperties ? '▼' : '▶'}</span>
                                    {t('character.properties')} <span className="field-hint">({t('character.propertiesHint')})</span>
                                </h4>
                            </div>
                            {showProperties && (
                                <PropertiesEditor
                                    properties={selectedChar.properties || {}}
                                    onChange={(newProps) => updateSelectedChar({ properties: newProps })}
                                />
                            )}
                        </div>

                        {/* Location */}
                        <div className="placement-manager">
                            <div className="section-header">
                                <h4>{t('character.startingLocation')}</h4>
                            </div>

                            <div className="placement-list">
                                <div className="placement-item">
                                    <div className="placement-info">
                                        <div className="placement-node">
                                            {selectedChar.properties?.location
                                                ? (nodes[selectedChar.properties.location]?.name || selectedChar.properties.location)
                                                : t('character.noStartingLocation')}
                                        </div>
                                        <div className="placement-config">
                                            <select
                                                value={selectedChar.properties?.location || ''}
                                                onChange={(e) => handleLocationChange(e.target.value)}
                                            >
                                                <option value="">{t('character.noLocation')}</option>
                                                {availableNodes.map(node => (
                                                    <option key={node.id} value={node.id}>
                                                        {node.name || node.id}
                                                    </option>
                                                ))}
                                            </select>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* Capabilities */}
                        <div className="capabilities-section">
                            <h4>{t('character.capabilities')}</h4>
                            <div className="checkbox-group">
                                <label className="checkbox-item">
                                    <input
                                        type="checkbox"
                                        checked={selectedChar.is_playable || false}
                                        onChange={(e) => updateSelectedChar({ is_playable: e.target.checked })}
                                    />
                                    <span>{t('character.playable')}</span>
                                </label>
                                <label className="checkbox-item">
                                    <input
                                        type="checkbox"
                                        checked={selectedChar.is_hittable || false}
                                        onChange={(e) => updateSelectedChar({ is_hittable: e.target.checked })}
                                    />
                                    <span>{t('character.combat')}</span>
                                </label>
                            </div>
                        </div>

                        <div className="section">
                            <div className="section-header">
                                <h4>{t('character.interactionGuidance')}</h4>
                            </div>
                            <div className="actions-empty-state">
                                {t('character.interactionDeprecated')}
                            </div>
                        </div>

                        <button
                            className="delete-character-btn"
                            onClick={(e) => handleDeleteCharacter(selectedChar.id, e)}
                        >
                            {t('character.delete')}
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
};

export default CharacterPanel;
