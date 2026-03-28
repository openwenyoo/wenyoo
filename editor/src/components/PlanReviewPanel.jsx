import React, { useState, useMemo } from 'react';
import '../styles/plan-review.css';
import { useLocale } from '../i18n';

/**
 * PlanReviewPanel - Displays an execution plan for user review before execution.
 * 
 * This allows users to see what changes will be made before they happen,
 * and optionally edit the plan or cancel.
 */
const PlanReviewPanel = ({
    isOpen,
    plan,
    onExecute,
    onEdit,
    onCancel,
    isExecuting = false,
    currentStep = null,
    executionProgress = 0
}) => {
    const { t } = useLocale();
    const [expandedSteps, setExpandedSteps] = useState(new Set());
    
    // Extract plan data with safe defaults - must be before any early returns after hooks
    const steps = useMemo(() => {
        if (!plan || !Array.isArray(plan.steps)) return [];
        return plan.steps;
    }, [plan]);
    
    const planType = plan?.plan_type || 'unknown';
    const planScope = plan?.scope || 'unknown';
    const summary = plan?.summary || '';
    
    // Group steps by category for display
    const stepGroups = useMemo(() => {
        const groups = {
            parameters: [],
            characters: [],
            nodes: [],
            objects: []
        };
        
        if (!steps || steps.length === 0) return groups;
        
        for (const step of steps) {
            if (!step) continue;
            const action = step.action || '';
            if (action.includes('parameter') || action.includes('lorebook')) {
                groups.parameters.push(step);
            } else if (action.includes('character')) {
                groups.characters.push(step);
            } else if (action.includes('node') || action.includes('action') || action.includes('object_to_node')) {
                groups.nodes.push(step);
            } else if (action.includes('object')) {
                groups.objects.push(step);
            } else {
                groups.nodes.push(step); // Default to nodes
            }
        }
        
        return groups;
    }, [steps]);
    
    // Early return AFTER all hooks
    if (!isOpen || !plan) return null;
    
    const toggleStep = (stepId) => {
        const newExpanded = new Set(expandedSteps);
        if (newExpanded.has(stepId)) {
            newExpanded.delete(stepId);
        } else {
            newExpanded.add(stepId);
        }
        setExpandedSteps(newExpanded);
    };
    
    const getActionIcon = (action) => {
        if (action.includes('create')) return '➕';
        if (action.includes('update') || action.includes('add_')) return '✏️';
        if (action.includes('delete')) return '🗑️';
        if (action.includes('set')) return '⚙️';
        return '📝';
    };
    
    const getStepStatus = (stepId) => {
        if (currentStep === stepId) return 'executing';
        if (steps.findIndex(s => s.id === stepId) < steps.findIndex(s => s.id === currentStep)) {
            return 'completed';
        }
        return 'pending';
    };
    
    return (
        <div className="plan-review-overlay">
            <div className="plan-review-panel">
                <div className="plan-review-header">
                    <h2>{t('plan.reviewTitle')}</h2>
                    {!isExecuting && (
                        <button className="plan-close-btn" onClick={onCancel}>×</button>
                    )}
                </div>
                
                <div className="plan-review-content">
                    {/* Summary Section */}
                    <div className="plan-summary">
                        <div className="plan-type-badge" data-type={planType}>
                            {planType.replace('_', ' ')}
                        </div>
                        <div className="plan-scope-badge" data-scope={planScope}>
                            {planScope.replace('_', ' ')}
                        </div>
                        <p className="plan-summary-text">{summary}</p>
                    </div>
                    
                    {/* Estimated Changes */}
                    {plan.estimated_changes && (
                        <div className="plan-estimates">
                            <h4>{t('plan.estimatedChanges')}</h4>
                            <div className="estimate-chips">
                                {plan.estimated_changes.nodes_created > 0 && (
                                    <span className="estimate-chip nodes">
                                        {t('plan.nodesCreated', { count: plan.estimated_changes.nodes_created })}
                                    </span>
                                )}
                                {plan.estimated_changes.nodes_modified > 0 && (
                                    <span className="estimate-chip modified">
                                        {t('plan.nodesModified', { count: plan.estimated_changes.nodes_modified })}
                                    </span>
                                )}
                                {plan.estimated_changes.characters_created > 0 && (
                                    <span className="estimate-chip characters">
                                        {t('plan.charactersCreated', { count: plan.estimated_changes.characters_created })}
                                    </span>
                                )}
                                {plan.estimated_changes.parameters_set > 0 && (
                                    <span className="estimate-chip params">
                                        {t('plan.parametersSet', { count: plan.estimated_changes.parameters_set })}
                                    </span>
                                )}
                            </div>
                        </div>
                    )}
                    
                    {/* Lore Outline Preview */}
                    {plan.lore_outline && typeof plan.lore_outline === 'string' && (
                        <div className="plan-lore-preview">
                            <h4>{t('plan.storyOutline')}</h4>
                            <pre className="lore-text">
                                {plan.lore_outline.length > 300 
                                    ? plan.lore_outline.slice(0, 300) + '...' 
                                    : plan.lore_outline}
                            </pre>
                        </div>
                    )}
                    
                    {/* Execution Progress */}
                    {isExecuting && (
                        <div className="execution-progress">
                            <div className="progress-bar">
                                <div 
                                    className="progress-fill" 
                                    style={{ width: `${executionProgress}%` }}
                                />
                            </div>
                            <span className="progress-text">
                                {t('plan.executingStep', { current: currentStep, total: steps.length })}
                            </span>
                        </div>
                    )}
                    
                    {/* Steps List */}
                    <div className="plan-steps">
                        <h4>{t('plan.executionSteps', { count: steps.length })}</h4>
                        
                        {/* Group: Parameters */}
                        {stepGroups.parameters.length > 0 && (
                            <div className="step-group">
                                <h5>{`📋 ${t('plan.groupParameters')}`}</h5>
                                {stepGroups.parameters.map(step => (
                                    <StepItem 
                                        key={step.id}
                                        step={step}
                                        status={isExecuting ? getStepStatus(step.id) : 'pending'}
                                        isExpanded={expandedSteps.has(step.id)}
                                        onToggle={() => toggleStep(step.id)}
                                        getIcon={getActionIcon}
                                    />
                                ))}
                            </div>
                        )}
                        
                        {/* Group: Characters */}
                        {stepGroups.characters.length > 0 && (
                            <div className="step-group">
                                <h5>{`👤 ${t('plan.groupCharacters')}`}</h5>
                                {stepGroups.characters.map(step => (
                                    <StepItem 
                                        key={step.id}
                                        step={step}
                                        status={isExecuting ? getStepStatus(step.id) : 'pending'}
                                        isExpanded={expandedSteps.has(step.id)}
                                        onToggle={() => toggleStep(step.id)}
                                        getIcon={getActionIcon}
                                    />
                                ))}
                            </div>
                        )}
                        
                        {/* Group: Nodes */}
                        {stepGroups.nodes.length > 0 && (
                            <div className="step-group">
                                <h5>{`📍 ${t('plan.groupNodes')}`}</h5>
                                {stepGroups.nodes.map(step => (
                                    <StepItem 
                                        key={step.id}
                                        step={step}
                                        status={isExecuting ? getStepStatus(step.id) : 'pending'}
                                        isExpanded={expandedSteps.has(step.id)}
                                        onToggle={() => toggleStep(step.id)}
                                        getIcon={getActionIcon}
                                    />
                                ))}
                            </div>
                        )}
                        
                        {/* Group: Objects */}
                        {stepGroups.objects.length > 0 && (
                            <div className="step-group">
                                <h5>{`📦 ${t('plan.groupObjects')}`}</h5>
                                {stepGroups.objects.map(step => (
                                    <StepItem 
                                        key={step.id}
                                        step={step}
                                        status={isExecuting ? getStepStatus(step.id) : 'pending'}
                                        isExpanded={expandedSteps.has(step.id)}
                                        onToggle={() => toggleStep(step.id)}
                                        getIcon={getActionIcon}
                                    />
                                ))}
                            </div>
                        )}
                    </div>
                </div>
                
                {/* Action Buttons */}
                <div className="plan-review-actions">
                    {!isExecuting ? (
                        <>
                            <button 
                                className="plan-btn plan-btn-secondary"
                                onClick={onCancel}
                            >
                                {t('generic.cancel')}
                            </button>
                            {onEdit && (
                                <button 
                                    className="plan-btn plan-btn-edit"
                                    onClick={() => onEdit(plan)}
                                >
                                    {t('plan.editPlan')}
                                </button>
                            )}
                            <button 
                                className="plan-btn plan-btn-primary"
                                onClick={() => onExecute(plan)}
                            >
                                {t('plan.executePlan')}
                            </button>
                        </>
                    ) : (
                        <div className="executing-indicator">
                            <div className="executing-spinner"></div>
                            <span>{t('plan.executing')}</span>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
};

/**
 * Individual step item in the plan
 */
const StepItem = ({ step, status, isExpanded, onToggle, getIcon }) => {
    const { t } = useLocale();
    const action = step.action || 'unknown';
    const params = step.params || {};
    const stepId = step.id ?? '?';
    const description = step.description || `${action}(${params.id || params.key || '...'})`;
    
    return (
        <div className={`step-item ${status}`}>
            <div className="step-header" onClick={onToggle}>
                <span className="step-icon">{getIcon(action)}</span>
                <span className="step-id">#{stepId}</span>
                <span className="step-description">{description}</span>
                <span className={`step-status-icon ${status}`}>
                    {status === 'completed' && '✓'}
                    {status === 'executing' && '⟳'}
                    {status === 'pending' && '○'}
                </span>
                <span className="step-expand-icon">{isExpanded ? '▼' : '▶'}</span>
            </div>
            {isExpanded && (
                <div className="step-details">
                    <div className="step-action">
                        <strong>{t('plan.action')}</strong> {action}
                    </div>
                    <div className="step-params">
                        <strong>{t('plan.parameters')}</strong>
                        <pre>{JSON.stringify(params, null, 2)}</pre>
                    </div>
                </div>
            )}
        </div>
    );
};

export default PlanReviewPanel;
