import React, { useState } from 'react';
import '../styles/plan-review.css';
import { useLocale } from '../i18n';

/**
 * OutlineSelector - Story creation wizard for selecting and refining story outlines.
 * 
 * Phase 1: User provides a vague idea
 * Phase 2: AI generates multiple outline options
 * Phase 3: User selects/edits an outline (with per-card edit and AI-modify)
 * Phase 4: AI expands to detailed structure
 * Phase 5: User confirms and conducts story creation
 * Phase 6: Story conducting with parallel LLM expansion
 */
const OutlineSelector = ({
    isOpen,
    onClose,
    onDetailedBack,
    onStoryComplete,  // Called when complete story is ready (replaces onPlanReady)
    onPlanReady,      // Fallback: Called when plan is ready for execution (legacy)
    onNodeCreated,    // Called when a node is created/expanded during conducting (for real-time graph update)
    generateOutlines,  // Function to call for outline generation
    expandOutline,     // Function to expand selected outline
    refineOutline,     // Function to refine a single outline with AI (optional)
    refineOutlines,    // Function to refine current outline options in place
    refineDetailedOutline, // Function to refine detailed outline + plan in place
    executePlan,       // Function to execute skeleton plan
    conductStory,      // Function to conduct story expansion with parallel LLM
    // Initial state props (set by AI panel before opening)
    initialIdea = '',
    initialPhase = null, // null, 'selecting', 'detailed'
    initialOutlines = [],
    initialDetailedOutline = null,
    initialPlan = null,
}) => {
    const { t } = useLocale();
    const [phase, setPhase] = useState('idea'); // idea, generating, selecting, expanding, detailed, conducting
    const [idea, setIdea] = useState('');
    const [outlines, setOutlines] = useState([]);
    const [selectedOutlineIndex, setSelectedOutlineIndex] = useState(null);
    const [customOutline, setCustomOutline] = useState('');
    const [useCustom, setUseCustom] = useState(false);
    const [detailedOutline, setDetailedOutline] = useState(null);
    const [plan, setPlan] = useState(null);
    const [modifications, setModifications] = useState('');
    const [error, setError] = useState(null);
    const [isLoading, setIsLoading] = useState(false);
    const [initialized, setInitialized] = useState(false);
    
    // Per-card editing state
    const [editingIndex, setEditingIndex] = useState(null);
    const [editFormData, setEditFormData] = useState({});
    const [modifyComment, setModifyComment] = useState('');
    const [isModifying, setIsModifying] = useState(false);
    const [selectionAssistantPrompt, setSelectionAssistantPrompt] = useState('');
    const [detailedAssistantPrompt, setDetailedAssistantPrompt] = useState('');
    const [isRefiningSelection, setIsRefiningSelection] = useState(false);
    const [isRefiningDetailed, setIsRefiningDetailed] = useState(false);
    
    // Conducting phase state
    const [conductingPhase, setConductingPhase] = useState(''); // skeleton, expanding, connecting
    const [conductingMessage, setConductingMessage] = useState('');
    const [nodesProgress, setNodesProgress] = useState({ current: 0, total: 0 });
    const [expandedNodes, setExpandedNodes] = useState([]);
    const [conductingErrors, setConductingErrors] = useState([]);
    
    // Initialize from props when opened with initial state
    React.useEffect(() => {
        if (isOpen && !initialized) {
            if (initialPhase) {
                setIdea(initialIdea);
                setPhase(initialPhase);
                setOutlines(initialOutlines || []);
                setDetailedOutline(initialDetailedOutline);
                setPlan(initialPlan);
                setInitialized(true);
            }
        }
        // Reset initialized when closed
        if (!isOpen) {
            setInitialized(false);
        }
    }, [isOpen, initialPhase, initialIdea, initialOutlines, initialDetailedOutline, initialPlan, initialized]);
    
    if (!isOpen) return null;
    
    const handleGenerateOutlines = async () => {
        if (!idea.trim()) return;
        
        setPhase('generating');
        setIsLoading(true);
        setError(null);
        
        try {
            const result = await generateOutlines(idea, 3);
            setOutlines(result);
            setSelectedOutlineIndex(null);
            setUseCustom(false);
            setPhase('selecting');
        } catch (err) {
            setError(err.message);
            setPhase('idea');
        } finally {
            setIsLoading(false);
        }
    };
    
    const handleRegenerateOutlines = async () => {
        // Regenerate without clearing custom outline
        setPhase('generating');
        setIsLoading(true);
        setError(null);
        setSelectedOutlineIndex(null);
        
        try {
            const result = await generateOutlines(idea, 3);
            setOutlines(result);
            setPhase('selecting');
        } catch (err) {
            setError(err.message);
            setPhase('selecting');
        } finally {
            setIsLoading(false);
        }
    };
    
    const handleSelectOutline = (index) => {
        setSelectedOutlineIndex(index);
        setUseCustom(false);
        setEditingIndex(null);
    };
    
    const handleSelectCustom = () => {
        setSelectedOutlineIndex(null);
        setUseCustom(true);
        setEditingIndex(null);
    };
    
    // Start editing a specific outline card
    const handleStartEdit = (index, e) => {
        e.stopPropagation();
        const outline = outlines[index];
        setEditingIndex(index);
        setEditFormData({
            title: outline.title || '',
            theme: outline.theme || '',
            setting_location: outline.setting?.location || '',
            setting_time: outline.setting?.time_period || '',
            core_conflict: outline.core_conflict || '',
            key_features: (outline.key_features || []).join(', ')
        });
        setModifyComment('');
    };
    
    // Save manual edits
    const handleSaveEdit = (index) => {
        const updatedOutlines = [...outlines];
        updatedOutlines[index] = {
            ...updatedOutlines[index],
            title: editFormData.title,
            theme: editFormData.theme,
            setting: {
                ...updatedOutlines[index].setting,
                location: editFormData.setting_location,
                time_period: editFormData.setting_time
            },
            core_conflict: editFormData.core_conflict,
            key_features: editFormData.key_features.split(',').map(f => f.trim()).filter(f => f)
        };
        setOutlines(updatedOutlines);
        setEditingIndex(null);
        setSelectedOutlineIndex(index);
    };
    
    const handleCancelEdit = () => {
        setEditingIndex(null);
        setEditFormData({});
        setModifyComment('');
    };
    
    // AI-assisted modification of a single outline
    const handleModifyWithAI = async (index) => {
        if (!modifyComment.trim() || !refineOutline) return;
        
        setIsModifying(true);
        try {
            const outline = outlines[index];
            const refined = await refineOutline(outline, modifyComment);
            
            const updatedOutlines = [...outlines];
            updatedOutlines[index] = {
                ...updatedOutlines[index],
                ...refined
            };
            setOutlines(updatedOutlines);
            setEditingIndex(null);
            setModifyComment('');
            setSelectedOutlineIndex(index);
        } catch (err) {
            setError(t('outline.failedModify', { error: err.message }));
        } finally {
            setIsModifying(false);
        }
    };
    
    const handleConfirmSelection = async () => {
        let outlineToExpand;
        
        if (useCustom) {
            outlineToExpand = { 
                title: t('outline.customTitle'),
                theme: customOutline,
                core_conflict: customOutline 
            };
        } else if (selectedOutlineIndex !== null) {
            outlineToExpand = outlines[selectedOutlineIndex];
        } else {
            return;
        }
        
        setPhase('expanding');
        setIsLoading(true);
        setError(null);
        
        try {
            const result = await expandOutline(outlineToExpand, modifications || null);
            setDetailedOutline(result.detailedOutline);
            setPlan(result.plan);
            setPhase('detailed');
        } catch (err) {
            setError(err.message);
            setPhase('selecting');
        } finally {
            setIsLoading(false);
        }
    };

    const handleRefineSelectionScope = async () => {
        if (!selectionAssistantPrompt.trim() || !refineOutlines || outlines.length === 0) return;

        setIsRefiningSelection(true);
        setError(null);

        try {
            const result = await refineOutlines(outlines, selectionAssistantPrompt, selectedOutlineIndex);
            setOutlines(result.outlines);
            if (typeof result.selectedIndex === 'number') {
                setSelectedOutlineIndex(result.selectedIndex);
                setUseCustom(false);
            }
            setEditingIndex(null);
            setSelectionAssistantPrompt('');
        } catch (err) {
            setError(t('outline.failedDirections', { error: err.message }));
        } finally {
            setIsRefiningSelection(false);
        }
    };

    const handleRefineDetailedScope = async () => {
        if (!detailedAssistantPrompt.trim() || !refineDetailedOutline || !detailedOutline) return;

        setIsRefiningDetailed(true);
        setError(null);

        try {
            const result = await refineDetailedOutline(detailedOutline, detailedAssistantPrompt);
            setDetailedOutline(result.detailedOutline);
            setPlan(result.plan);
            setDetailedAssistantPrompt('');
        } catch (err) {
            setError(t('outline.failedReview', { error: err.message }));
        } finally {
            setIsRefiningDetailed(false);
        }
    };
    
    const handleExecutePlan = async () => {
        if (!plan) return;
        
        // If we have conductStory and executePlan, use the full conducting flow
        if (conductStory && executePlan) {
            setPhase('conducting');
            setConductingPhase('skeleton');
            setConductingMessage(t('outline.creatingSkeleton'));
            setExpandedNodes([]);
            setConductingErrors([]);
            setNodesProgress({ current: 0, total: 0 });
            
            try {
                // Phase 1: Execute the skeleton plan
                const skeletonResult = await new Promise((resolve, reject) => {
                    executePlan({
                        plan,
                        nodes: [],
                        edges: [],
                        characters: [],
                        objects: [],
                        parameters: {},
                        onThinking: (msg) => setConductingMessage(msg),
                        onNodeCreated: (node) => {
                            setConductingMessage(t('outline.createdNode', { name: node?.data?.name || node?.id || 'node' }));
                            // Add skeleton node to the graph immediately
                            if (onNodeCreated && node?.id) {
                                const nodeData = node.data || {};
                                onNodeCreated(node.id, {
                                    id: node.id,
                                    name: nodeData.name || node.id,
                                    definition: nodeData.definition || '',
                                    explicit_state: nodeData.explicit_state || t('outline.expandingPlaceholder'),
                                    implicit_state: nodeData.implicit_state || '',
                                    properties: nodeData.properties || {},
                                    actions: nodeData.actions || [],
                                    objects: nodeData.objects || [],
                                    triggers: nodeData.triggers || [],
                                    isSkeleton: true  // Mark as skeleton for styling
                                });
                            }
                        },
                        onCharacterCreated: (char) => {
                            setConductingMessage(t('outline.createdCharacter', { name: char?.name || char?.id || 'character' }));
                        },
                        onComplete: (result) => resolve(result),
                        onError: (error) => reject(new Error(error))
                    });
                });
                
                // Build skeleton from the result
                const skeleton = skeletonResult.finalState || {};
                
                // Phase 2: Conduct story expansion (sequential - one node at a time)
                setConductingPhase('expanding');
                setConductingMessage(t('outline.expandingRich'));
                
                const finalStory = await conductStory(skeleton, detailedOutline, {
                    onPhaseStart: (phase, message, data) => {
                        setConductingPhase(phase);
                        setConductingMessage(message);
                        if (data?.total_nodes) {
                            setNodesProgress(prev => ({ ...prev, total: data.total_nodes }));
                        }
                    },
                    onNodeExpanding: (nodeId, nodeName, progress) => {
                        setConductingMessage(t('outline.expandingNode', { name: nodeName }));
                    },
                    onNodeComplete: (nodeId, nodeName, info) => {
                        setExpandedNodes(prev => [...prev, { nodeId, nodeName, ...info }]);
                        setNodesProgress(prev => ({ ...prev, current: prev.current + 1 }));
                        setConductingMessage(t('outline.completedNode', { name: nodeName, actions: info.actionsCount }));
                        
                        // Update the main graph in real-time with the expanded node
                        if (onNodeCreated && info.nodeData) {
                            onNodeCreated(nodeId, info.nodeData);
                        }
                    },
                    onNodeError: (nodeId, error) => {
                        setConductingErrors(prev => [...prev, { nodeId, error }]);
                    },
                    onCharacterPlaced: (charId, nodeId) => {
                        setConductingMessage(t('outline.placedCharacter', { characterId: charId, nodeId }));
                    },
                    onConnectionsCreating: (count) => {
                        setConductingPhase('connecting');
                        setConductingMessage(t('outline.creatingConnections', { count }));
                    },
                    onComplete: (result) => {
                        setConductingMessage(result.message);
                    },
                    onError: (error) => {
                        throw new Error(error);
                    }
                });
                
                // Story complete!
                if (!finalStory) {
                    throw new Error(t('outline.noStoryReturned'));
                }
                
                setConductingMessage(t('outline.storyCreated'));
                setConductingPhase('complete');
                
                // Small delay to show success message
                await new Promise(resolve => setTimeout(resolve, 500));
                
                if (onStoryComplete) {
                    onStoryComplete(finalStory, detailedOutline);
                } else if (onPlanReady) {
                    // Fallback to legacy behavior
                    onPlanReady(plan, detailedOutline);
                }
                
            } catch (err) {
                console.error('Story creation error:', err);
                setError(err.message || t('outline.storyCreationError'));
                setPhase('detailed');
            }
        } else {
            // Fallback: just pass the plan for legacy execution
            if (onPlanReady) {
                onPlanReady(plan, detailedOutline);
            }
        }
    };
    
    const handleBack = () => {
        if (phase === 'selecting') {
            setPhase('idea');
            setOutlines([]);
            setEditingIndex(null);
        } else if (phase === 'detailed') {
            if (onDetailedBack && (!outlines || outlines.length === 0) && !useCustom) {
                onDetailedBack();
            } else {
                setPhase('selecting');
                setDetailedOutline(null);
                setPlan(null);
            }
        }
    };
    
    const canProceed = useCustom ? customOutline.trim() : selectedOutlineIndex !== null;
    
    // Compact mode during conducting - wizard moves to corner
    const isCompactMode = phase === 'conducting';
    
    return (
        <div className={`outline-selector-overlay ${isCompactMode ? 'compact-mode' : ''}`}>
            <div className={`outline-selector-panel ${isCompactMode ? 'compact' : ''}`}>
                <div className="outline-header">
                    <h2>{isCompactMode ? t('outline.creatingTitle') : t('outline.title')}</h2>
                    {!isCompactMode && (
                        <button className="outline-close-btn" onClick={onClose}>×</button>
                    )}
                </div>
                
                {/* Progress Indicator - hide in compact mode */}
                {!isCompactMode && (
                    <div className="outline-progress">
                        <div className={`progress-step ${phase === 'idea' || phase === 'generating' ? 'active' : 'completed'}`}>
                            <span className="step-num">1</span>
                            <span className="step-label">{t('outline.stepIdea')}</span>
                        </div>
                        <div className="progress-line"></div>
                        <div className={`progress-step ${phase === 'selecting' ? 'active' : ['detailed', 'expanding', 'conducting'].includes(phase) ? 'completed' : ''}`}>
                            <span className="step-num">2</span>
                            <span className="step-label">{t('outline.stepChoose')}</span>
                        </div>
                        <div className="progress-line"></div>
                        <div className={`progress-step ${phase === 'detailed' || phase === 'expanding' ? 'active' : phase === 'conducting' ? 'completed' : ''}`}>
                            <span className="step-num">3</span>
                            <span className="step-label">{t('outline.stepReview')}</span>
                        </div>
                        <div className="progress-line"></div>
                        <div className={`progress-step ${phase === 'conducting' ? 'active' : ''}`}>
                            <span className="step-num">4</span>
                            <span className="step-label">{t('outline.stepCreating')}</span>
                        </div>
                    </div>
                )}
                
                <div className="outline-content">
                    {error && (
                        <div className="outline-error">
                            <span className="error-icon">!</span>
                            <span>{error}</span>
                            <button onClick={() => setError(null)}>×</button>
                        </div>
                    )}
                    
                    {/* Phase 1: Enter Idea */}
                    {phase === 'idea' && (
                        <div className="outline-phase idea-phase">
                            <h3>{t('outline.ideaTitle')}</h3>
                            <p className="phase-hint">
                                {t('outline.ideaHint')}
                            </p>
                            <textarea
                                value={idea}
                                onChange={(e) => setIdea(e.target.value)}
                                placeholder={t('outline.ideaPlaceholder')}
                                autoFocus
                            />
                            <button 
                                className="outline-btn primary"
                                onClick={handleGenerateOutlines}
                                disabled={!idea.trim()}
                            >
                                {t('outline.generateIdeas')}
                            </button>
                        </div>
                    )}
                    
                    {/* Loading State */}
                    {(phase === 'generating' || phase === 'expanding') && (
                        <div className="outline-phase loading-phase">
                            <div className="loading-animation">
                                <div className="loading-spinner large"></div>
                            </div>
                            <h3>{phase === 'generating' ? t('outline.generatingIdeas') : t('outline.creatingStoryLoading')}</h3>
                            <p className="phase-hint">
                                {phase === 'generating' 
                                    ? t('outline.generatingHint')
                                    : t('outline.creatingHint')}
                            </p>
                        </div>
                    )}
                    
                    {/* Phase 2: Select Outline */}
                    {phase === 'selecting' && (
                        <div className="outline-phase selecting-phase">
                            <div className="selecting-header">
                                <div>
                                    <h3>{t('outline.selectTitle')}</h3>
                                    <p className="phase-hint">
                                        {t('outline.selectHint')}
                                    </p>
                                </div>
                                <button 
                                    className="outline-btn secondary regenerate-btn"
                                    onClick={handleRegenerateOutlines}
                                    disabled={isLoading}
                                    title={t('outline.regenerateTitle')}
                                >
                                    {t('outline.regenerate')}
                                </button>
                            </div>
                            
                            {/* AI-Generated Options */}
                            <div className="outline-options">
                                {outlines.map((outline, index) => (
                                    <div 
                                        key={outline.id || index}
                                        className={`outline-card ${selectedOutlineIndex === index ? 'selected' : ''} ${editingIndex === index ? 'editing' : ''}`}
                                        onClick={() => editingIndex !== index && handleSelectOutline(index)}
                                    >
                                        {editingIndex === index ? (
                                            // Editing mode
                                            <div className="outline-card-edit" onClick={(e) => e.stopPropagation()}>
                                                <div className="edit-field">
                                                    <label>{t('outline.fieldTitle')}</label>
                                                    <input 
                                                        type="text"
                                                        value={editFormData.title}
                                                        onChange={(e) => setEditFormData({...editFormData, title: e.target.value})}
                                                    />
                                                </div>
                                                <div className="edit-field">
                                                    <label>{t('outline.fieldTheme')}</label>
                                                    <input 
                                                        type="text"
                                                        value={editFormData.theme}
                                                        onChange={(e) => setEditFormData({...editFormData, theme: e.target.value})}
                                                    />
                                                </div>
                                                <div className="edit-row">
                                                    <div className="edit-field">
                                                        <label>{t('outline.fieldSetting')}</label>
                                                        <input 
                                                            type="text"
                                                            value={editFormData.setting_location}
                                                            onChange={(e) => setEditFormData({...editFormData, setting_location: e.target.value})}
                                                            placeholder={t('outline.fieldLocation')}
                                                        />
                                                    </div>
                                                    <div className="edit-field">
                                                        <label>{t('outline.fieldTime')}</label>
                                                        <input 
                                                            type="text"
                                                            value={editFormData.setting_time}
                                                            onChange={(e) => setEditFormData({...editFormData, setting_time: e.target.value})}
                                                            placeholder={t('outline.timePlaceholder')}
                                                        />
                                                    </div>
                                                </div>
                                                <div className="edit-field">
                                                    <label>{t('outline.fieldConflict')}</label>
                                                    <textarea
                                                        value={editFormData.core_conflict}
                                                        onChange={(e) => setEditFormData({...editFormData, core_conflict: e.target.value})}
                                                        rows={2}
                                                    />
                                                </div>
                                                <div className="edit-field">
                                                    <label>{t('outline.fieldFeatures')}</label>
                                                    <input 
                                                        type="text"
                                                        value={editFormData.key_features}
                                                        onChange={(e) => setEditFormData({...editFormData, key_features: e.target.value})}
                                                    />
                                                </div>
                                                
                                                {/* AI Modification Section */}
                                                {refineOutline && (
                                                    <div className="ai-modify-section">
                                                        <label>{t('outline.aiChangesLabel')}</label>
                                                        <div className="ai-modify-input">
                                                            <input 
                                                                type="text"
                                                                value={modifyComment}
                                                                onChange={(e) => setModifyComment(e.target.value)}
                                                                placeholder={t('outline.aiChangesPlaceholder')}
                                                                disabled={isModifying}
                                                            />
                                                            <button 
                                                                className="outline-btn small primary"
                                                                onClick={() => handleModifyWithAI(index)}
                                                                disabled={!modifyComment.trim() || isModifying}
                                                            >
                                                                {isModifying ? '...' : t('generic.apply')}
                                                            </button>
                                                        </div>
                                                    </div>
                                                )}
                                                
                                                <div className="edit-actions">
                                                    <button className="outline-btn small secondary" onClick={handleCancelEdit}>
                                                        {t('generic.cancel')}
                                                    </button>
                                                    <button className="outline-btn small primary" onClick={() => handleSaveEdit(index)}>
                                                        {t('outline.saveChanges')}
                                                    </button>
                                                </div>
                                            </div>
                                        ) : (
                                            // Display mode
                                            <>
                                                <div className="outline-card-header">
                                                    <h4>{outline.title}</h4>
                                                    <div className="card-header-actions">
                                                        <span className={`length-badge ${outline.estimated_length}`}>
                                                            {outline.estimated_length}
                                                        </span>
                                                        <button 
                                                            className="card-edit-btn"
                                                            onClick={(e) => handleStartEdit(index, e)}
                                                            title={t('outline.editDirectionTitle')}
                                                        >
                                                            ✎
                                                        </button>
                                                    </div>
                                                </div>
                                                <div className="outline-card-theme">
                                                    <strong>{t('outline.themeLabel')}</strong> {outline.theme}
                                                </div>
                                                <div className="outline-card-setting">
                                                    <strong>{t('outline.settingLabel')}</strong> {outline.setting?.location || t('outline.tbd')}, {outline.setting?.time_period || ''}
                                                </div>
                                                <div className="outline-card-conflict">
                                                    <strong>{t('outline.conflictLabel')}</strong> {outline.core_conflict}
                                                </div>
                                                {outline.key_features && (
                                                    <div className="outline-card-features">
                                                        {outline.key_features.slice(0, 3).map((f, i) => (
                                                            <span key={i} className="feature-tag">{f}</span>
                                                        ))}
                                                    </div>
                                                )}
                                            </>
                                        )}
                                    </div>
                                ))}
                            </div>
                            
                            {/* Custom Outline Section - Separated */}
                            <div className="custom-outline-section">
                                <div className="section-divider">
                                    <span>{t('outline.or')}</span>
                                </div>
                                <div 
                                    className={`custom-outline-box ${useCustom ? 'selected' : ''}`}
                                    onClick={handleSelectCustom}
                                >
                                    <h4>{t('outline.customTitle')}</h4>
                                    <textarea
                                        value={customOutline}
                                        onChange={(e) => {
                                            setCustomOutline(e.target.value);
                                            if (e.target.value) {
                                                setUseCustom(true);
                                                setSelectedOutlineIndex(null);
                                            }
                                        }}
                                        placeholder={t('outline.customPlaceholder')}
                                        onClick={(e) => e.stopPropagation()}
                                        rows={4}
                                    />
                                </div>
                            </div>
                            
                            {/* Optional modifications for selected outline */}
                            {selectedOutlineIndex !== null && (
                                <div className="modifications-section">
                                    <label>{t('outline.modificationsLabel')}</label>
                                    <input
                                        type="text"
                                        value={modifications}
                                        onChange={(e) => setModifications(e.target.value)}
                                        placeholder={t('outline.modificationsPlaceholder')}
                                    />
                                </div>
                            )}

                            {refineOutlines && outlines.length > 0 && (
                                <div className="wizard-assistant-box">
                                    <div className="wizard-assistant-header">
                                        <h4>{t('outline.aiAssistant')}</h4>
                                        <span>{t('outline.assistantSelectionHint')}</span>
                                    </div>
                                    <textarea
                                        value={selectionAssistantPrompt}
                                        onChange={(e) => setSelectionAssistantPrompt(e.target.value)}
                                        placeholder={t('outline.assistantSelectionPlaceholder')}
                                        rows={3}
                                        disabled={isRefiningSelection}
                                    />
                                    <div className="wizard-assistant-actions">
                                        <button
                                            className="outline-btn small primary"
                                            onClick={handleRefineSelectionScope}
                                            disabled={!selectionAssistantPrompt.trim() || isRefiningSelection}
                                        >
                                            {isRefiningSelection ? t('generic.applying') : t('outline.applyDirections')}
                                        </button>
                                    </div>
                                </div>
                            )}
                            
                            <div className="outline-actions">
                                <button className="outline-btn secondary" onClick={handleBack}>
                                    ← {t('generic.back')}
                                </button>
                                <button 
                                    className="outline-btn primary"
                                    onClick={handleConfirmSelection}
                                    disabled={!canProceed}
                                >
                                    {t('outline.developStory')}
                                </button>
                            </div>
                        </div>
                    )}
                    
                    {/* Phase 3: Detailed Review */}
                    {phase === 'detailed' && detailedOutline && (
                        <div className="outline-phase detailed-phase">
                            <h3>{detailedOutline.title || t('outline.reviewDefaultTitle')}</h3>
                            
                            {/* Theme & Setting */}
                            {(detailedOutline.theme || detailedOutline.setting) && (
                                <div className="story-overview">
                                    {detailedOutline.theme && <p><strong>{t('outline.themeLabel')}</strong> {detailedOutline.theme}</p>}
                                    {detailedOutline.setting && <p><strong>{t('outline.settingLabel')}</strong> {detailedOutline.setting}</p>}
                                    {detailedOutline.tone && <p><strong>{t('outline.overviewTone')}</strong> {detailedOutline.tone}</p>}
                                </div>
                            )}
                            
                            <div className="detailed-sections">
                                {/* Game Mechanics */}
                                {detailedOutline.game_mechanics && (
                                    <div className="detail-section">
                                        <h4>{t('outline.gameMechanics')}</h4>
                                        <div className="mechanics-info">
                                            {detailedOutline.game_mechanics.core_loop && (
                                                <p><strong>{t('outline.coreLoop')}</strong> {detailedOutline.game_mechanics.core_loop}</p>
                                            )}
                                            {detailedOutline.game_mechanics.key_variables?.length > 0 && (
                                                <div className="key-vars">
                                                    <strong>{t('outline.keyVariables')}</strong>
                                                    <div className="var-chips">
                                                        {detailedOutline.game_mechanics.key_variables.map((v, i) => (
                                                            <span key={i} className="var-chip" title={v.purpose}>
                                                                {v.name} ({v.type})
                                                            </span>
                                                        ))}
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                )}
                                
                                {/* Characters */}
                                {detailedOutline.characters?.length > 0 && (
                                    <div className="detail-section">
                                        <h4>{t('outline.characters', { count: detailedOutline.characters.length })}</h4>
                                        <div className="detail-items">
                                            {detailedOutline.characters.map((char, i) => (
                                                <div key={i} className="detail-item">
                                                    <strong>{char.name}</strong>
                                                    <span>{char.one_liner || char.role}</span>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}
                                
                                {/* Key Items */}
                                {detailedOutline.key_items?.length > 0 && (
                                    <div className="detail-section">
                                        <h4>{t('outline.keyItems', { count: detailedOutline.key_items.length })}</h4>
                                        <div className="detail-items">
                                            {detailedOutline.key_items.map((item, i) => (
                                                <div key={i} className="detail-item">
                                                    <strong>{item.name}</strong>
                                                    <span>{item.purpose}</span>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}
                                
                                {/* Major Locations */}
                                {detailedOutline.major_locations?.length > 0 && (
                                    <div className="detail-section">
                                        <h4>{t('outline.majorLocations')}</h4>
                                        <div className="location-chips">
                                            {detailedOutline.major_locations.map((loc, i) => (
                                                <span key={i} className="location-chip">{loc}</span>
                                            ))}
                                        </div>
                                    </div>
                                )}
                                
                                {/* Story Structure */}
                                {detailedOutline.story_structure && (
                                    <div className="detail-section">
                                        <h4>{t('outline.storyStructure')}</h4>
                                        <div className="story-acts">
                                            {detailedOutline.story_structure.act_1 && (
                                                <div className="story-act">
                                                    <span className="act-label">{t('outline.act1')}</span>
                                                    <span>{detailedOutline.story_structure.act_1}</span>
                                                </div>
                                            )}
                                            {detailedOutline.story_structure.act_2 && (
                                                <div className="story-act">
                                                    <span className="act-label">{t('outline.act2')}</span>
                                                    <span>{detailedOutline.story_structure.act_2}</span>
                                                </div>
                                            )}
                                            {detailedOutline.story_structure.act_3 && (
                                                <div className="story-act">
                                                    <span className="act-label">{t('outline.act3')}</span>
                                                    <span>{detailedOutline.story_structure.act_3}</span>
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                )}
                                
                                {/* Endings */}
                                {detailedOutline.endings?.length > 0 && (
                                    <div className="detail-section">
                                        <h4>{t('outline.possibleEndings')}</h4>
                                        <div className="detail-items endings">
                                            {detailedOutline.endings.map((ending, i) => (
                                                <div key={i} className={`detail-item ending ${ending.type || ''}`}>
                                                    <strong>{ending.title}</strong>
                                                    <span>{ending.trigger}</span>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}
                            </div>
                            
                            {/* Plan Summary */}
                            {plan && (
                                <div className="plan-summary-box">
                                    <h4>{t('outline.executionPlan')}</h4>
                                    <p>{plan.summary}</p>
                                    <div className="plan-stats">
                                        <span className="stat">{t('outline.planNodes', { count: plan.steps?.filter(s => s.action === 'create_node').length || 0 })}</span>
                                        <span className="stat">{t('outline.planCharacters', { count: plan.steps?.filter(s => s.action === 'create_character').length || 0 })}</span>
                                        <span className="stat">{t('outline.planTotalSteps', { count: plan.steps?.length || 0 })}</span>
                                    </div>
                                </div>
                            )}

                            {refineDetailedOutline && (
                                <div className="wizard-assistant-box">
                                    <div className="wizard-assistant-header">
                                        <h4>{t('outline.aiAssistant')}</h4>
                                        <span>{t('outline.assistantDetailedHint')}</span>
                                    </div>
                                    <textarea
                                        value={detailedAssistantPrompt}
                                        onChange={(e) => setDetailedAssistantPrompt(e.target.value)}
                                        placeholder={t('outline.assistantDetailedPlaceholder')}
                                        rows={3}
                                        disabled={isRefiningDetailed}
                                    />
                                    <div className="wizard-assistant-actions">
                                        <button
                                            className="outline-btn small primary"
                                            onClick={handleRefineDetailedScope}
                                            disabled={!detailedAssistantPrompt.trim() || isRefiningDetailed}
                                        >
                                            {isRefiningDetailed ? t('generic.applying') : t('outline.applyReview')}
                                        </button>
                                    </div>
                                </div>
                            )}
                            
                            <div className="outline-actions">
                                <button className="outline-btn secondary" onClick={handleBack}>
                                    ← {t('generic.modify')}
                                </button>
                                <button 
                                    className="outline-btn primary large"
                                    onClick={handleExecutePlan}
                                >
                                    {t('outline.createThisStory')}
                                </button>
                            </div>
                        </div>
                    )}
                    
                    {/* Phase 6: Conducting (Story Generation in Progress) */}
                    {phase === 'conducting' && (
                        <div className="outline-phase conducting-phase">
                            {/* Compact mode: minimal view - just status and progress */}
                            {isCompactMode ? (
                                <div className="compact-conducting">
                                    {/* Current Status with spinner */}
                                    <div className="conducting-status compact">
                                        <div className="loading-spinner"></div>
                                        <p className="conducting-message">{conductingMessage}</p>
                                    </div>
                                    
                                    {/* Simple Progress Bar */}
                                    {nodesProgress.total > 0 && (
                                        <div className="compact-progress">
                                            <div className="progress-bar-container">
                                                <div 
                                                    className="progress-bar-fill"
                                                    style={{ width: `${(nodesProgress.current / nodesProgress.total) * 100}%` }}
                                                ></div>
                                            </div>
                                            <span className="progress-text">
                                                {nodesProgress.current}/{nodesProgress.total}
                                            </span>
                                        </div>
                                    )}
                                </div>
                            ) : (
                                <>
                                    <h3>{t('outline.creatingYourStory')}</h3>
                                    
                                    {/* Progress Bar */}
                                    <div className="conducting-progress">
                                        <div className="conducting-phase-indicator">
                                            <span className={`phase-dot ${conductingPhase === 'skeleton' ? 'active' : conductingPhase !== 'skeleton' ? 'completed' : ''}`}>1</span>
                                            <span className="phase-name">{t('outline.phaseSkeleton')}</span>
                                        </div>
                                        <div className="phase-connector"></div>
                                        <div className="conducting-phase-indicator">
                                            <span className={`phase-dot ${conductingPhase === 'expanding' || conductingPhase === 'analyzing' ? 'active' : ['connecting', 'placing_characters'].includes(conductingPhase) ? 'completed' : ''}`}>2</span>
                                            <span className="phase-name">{t('outline.phaseExpanding')}</span>
                                        </div>
                                        <div className="phase-connector"></div>
                                        <div className="conducting-phase-indicator">
                                            <span className={`phase-dot ${conductingPhase === 'connecting' || conductingPhase === 'placing_characters' ? 'active' : ''}`}>3</span>
                                            <span className="phase-name">{t('outline.phaseConnecting')}</span>
                                        </div>
                                    </div>
                                    
                                    {/* Current Status */}
                                    <div className="conducting-status">
                                        <div className="loading-spinner"></div>
                                        <p className="conducting-message">{conductingMessage}</p>
                                    </div>
                                    
                                    {/* Nodes Progress */}
                                    {nodesProgress.total > 0 && (
                                        <div className="nodes-progress">
                                            <div className="progress-bar-container">
                                                <div 
                                                    className="progress-bar-fill"
                                                    style={{ width: `${(nodesProgress.current / nodesProgress.total) * 100}%` }}
                                                ></div>
                                            </div>
                                            <span className="progress-text">
                                                {t('outline.nodesExpanded', { current: nodesProgress.current, total: nodesProgress.total })}
                                            </span>
                                        </div>
                                    )}
                                    
                                    {/* Expanded Nodes List */}
                                    {expandedNodes.length > 0 && (
                                        <div className="expanded-nodes-list">
                                            <h4>{t('outline.completedNodes')}</h4>
                                            <div className="nodes-scroll">
                                                {expandedNodes.map((node, i) => (
                                                    <div key={i} className="expanded-node-item">
                                                        <span className="node-check">✓</span>
                                                        <span className="node-name">{node.nodeName}</span>
                                                        <span className="node-stats">
                                                            {t('outline.nodeStats', { actions: node.actionsCount, objects: node.objectsCount })}
                                                        </span>
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    )}
                                    
                                    {/* Errors (if any) */}
                                    {conductingErrors.length > 0 && (
                                        <div className="conducting-errors">
                                            <h4>{t('import.warnings')}</h4>
                                            {conductingErrors.map((err, i) => (
                                                <div key={i} className="error-item">
                                                    <span className="error-node">{err.nodeId}:</span>
                                                    <span className="error-msg">{err.error}</span>
                                                </div>
                                            ))}
                                        </div>
                                    )}
                                </>
                            )}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

export default OutlineSelector;
