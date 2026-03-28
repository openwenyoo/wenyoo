import React, { useState, useEffect } from 'react';
import ConditionEditor from './ConditionEditor';
import EffectListEditor from './EffectListEditor';
import { useLocale } from '../i18n';

const ActionEditor = ({ action = {}, onChange, onRemove, elementType = "action" }) => {
    const { t } = useLocale();
    const detailTypeLabel = elementType === 'trigger' ? t('trigger.singular') : t('action.singular');
    const [id, setId] = useState(action.id || '');
    const [name, setName] = useState(action.name || '');
    const [text, setText] = useState(action.text || '');
    const [intent, setIntent] = useState(action.intent || '');
    const [description, setDescription] = useState(action.description || '');
    const [feedback, setFeedback] = useState(action.feedback || '');
    const [conditions, setConditions] = useState(action.conditions || []);
    const [effects, setEffects] = useState(action.effects || []);

    useEffect(() => {
        setId(action.id || '');
        setName(action.name || '');
        setText(action.text || '');
        setIntent(action.intent || '');
        setDescription(action.description || '');
        setFeedback(action.feedback || '');
        setConditions(action.conditions || []);
        setEffects(action.effects || []);
    }, [action]);

    const updateParent = (updates) => {
        onChange({
            ...action,
            id: updates.id !== undefined ? updates.id : id,
            name: updates.name !== undefined ? updates.name : name,
            text: updates.text !== undefined ? updates.text : text,
            intent: updates.intent !== undefined ? updates.intent : intent,
            description: updates.description !== undefined ? updates.description : description,
            feedback: updates.feedback !== undefined ? updates.feedback : feedback,
            conditions: updates.conditions !== undefined ? updates.conditions : conditions,
            effects: updates.effects !== undefined ? updates.effects : effects,
        });
    };

    const handleFieldChange = (field, value) => {
        const setters = { id: setId, name: setName, text: setText, intent: setIntent, description: setDescription, feedback: setFeedback };
        setters[field]?.(value);
    };

    const handleBlur = () => {
        updateParent({ id, name, text, intent, description, feedback });
    };

    useEffect(() => {
        const timer = setTimeout(() => {
            const changed = [
                [name, action.name], [text, action.text], [id, action.id],
                [intent, action.intent], [description, action.description], [feedback, action.feedback]
            ].some(([cur, orig]) => (cur || '') !== (orig || ''));

            if (changed) {
                updateParent({ id, name, text, intent, description, feedback });
            }
        }, 800);
        return () => clearTimeout(timer);
    }, [id, name, text, intent, description, feedback]);

    const handleEffectsChange = (newEffects) => {
        setEffects(newEffects);
        updateParent({ effects: newEffects });
    };

    const addCondition = () => {
        const newConds = [...conditions, {}];
        setConditions(newConds);
        updateParent({ conditions: newConds });
    };

    const updateCondition = (idx, updated) => {
        const newConds = [...conditions];
        newConds[idx] = updated;
        setConditions(newConds);
        updateParent({ conditions: newConds });
    };

    const removeCondition = (idx) => {
        const newConds = conditions.filter((_, i) => i !== idx);
        setConditions(newConds);
        updateParent({ conditions: newConds });
    };

    const [showConditions, setShowConditions] = useState(conditions.length > 0);
    const [showEffects, setShowEffects] = useState(true);

    return (
        <div className="action-editor">
            <div className={`sticky-section-header type-${elementType}`}>
                {t('action.details', { type: detailTypeLabel })}
            </div>

            <div className="form-row two-col">
                <div className="form-group">
                    <label>{t('node.id')}</label>
                    <input
                        value={id}
                        onChange={(e) => handleFieldChange('id', e.target.value)}
                        onBlur={handleBlur}
                        placeholder={t('action.idPlaceholder')}
                    />
                </div>
                <div className="form-group">
                    <label>{t('node.name')}</label>
                    <input
                        value={name}
                        onChange={(e) => handleFieldChange('name', e.target.value)}
                        onBlur={handleBlur}
                        placeholder={t('action.namePlaceholder')}
                    />
                </div>
            </div>

            <div className="form-group">
                <label>{t('action.text')} <span className="field-hint">({t('action.textHint')})</span></label>
                <textarea
                    className="notebook-textarea"
                    value={text}
                    onChange={(e) => handleFieldChange('text', e.target.value)}
                    onBlur={handleBlur}
                    rows={2}
                    placeholder={t('action.textPlaceholder')}
                />
            </div>

            <div className="form-group">
                <label>{t('action.intent')} <span className="field-hint">({t('action.intentHint')})</span></label>
                <textarea
                    className="notebook-textarea"
                    value={intent}
                    onChange={(e) => handleFieldChange('intent', e.target.value)}
                    onBlur={handleBlur}
                    rows={4}
                    placeholder={t('action.intentPlaceholder')}
                />
            </div>

            <div className="form-group">
                <label>{t('action.description')} <span className="field-hint">({t('action.descriptionHint')})</span></label>
                <textarea
                    className="notebook-textarea"
                    value={description}
                    onChange={(e) => handleFieldChange('description', e.target.value)}
                    onBlur={handleBlur}
                    rows={2}
                    placeholder={t('action.descriptionPlaceholder')}
                />
            </div>

            <div className="form-group">
                <label>{t('action.feedback')} <span className="field-hint">({t('action.feedbackHint')})</span></label>
                <input
                    value={feedback}
                    onChange={(e) => handleFieldChange('feedback', e.target.value)}
                    onBlur={handleBlur}
                    placeholder={t('action.feedbackPlaceholder')}
                />
            </div>

            <div className="section collapsible-section">
                <div
                    className="section-header clickable"
                    onClick={() => setShowConditions(!showConditions)}
                >
                    <h4>
                        <span className="collapse-indicator">{showConditions ? '▼' : '▶'}</span>
                        {t('action.conditions')}
                        {conditions.length > 0 && <span className="count-badge">{conditions.length}</span>}
                    </h4>
                </div>
                {showConditions && (
                    <div className="conditions-list">
                        {conditions.map((cond, i) => (
                            <ConditionEditor
                                key={i}
                                condition={cond}
                                onChange={(updated) => updateCondition(i, updated)}
                                onRemove={() => removeCondition(i)}
                            />
                        ))}
                        <button className="add-button" onClick={addCondition}>{t('action.addCondition')}</button>
                    </div>
                )}
            </div>

            <div className="section collapsible-section">
                <div
                    className="section-header clickable"
                    onClick={() => {
                        if (!intent.trim()) {
                            setShowEffects(!showEffects);
                        }
                    }}
                    style={intent.trim() ? { opacity: 0.65, cursor: 'default' } : undefined}
                >
                    <h4>
                        <span className="collapse-indicator">{showEffects ? '▼' : '▶'}</span>
                        {t('action.effects')}
                        {effects.length > 0 && <span className="count-badge">{effects.length}</span>}
                    </h4>
                </div>
                {intent.trim() && (
                    <div className="info-box" style={{
                        padding: '8px 12px',
                        background: 'var(--color-info-bg, #e3f2fd)',
                        borderRadius: 0,
                        marginBottom: 12,
                        fontSize: '0.85rem',
                        border: '1px solid var(--color-border)'
                    }}>
                        {t('action.effectsIgnored')}
                    </div>
                )}
                {showEffects && (
                    <EffectListEditor
                        effects={effects}
                        onChange={handleEffectsChange}
                    />
                )}
            </div>

            {onRemove && (
                <div style={{ marginTop: 16, paddingTop: 16, borderTop: '1px solid var(--color-border)' }}>
                    <button className="remove-btn" onClick={onRemove}>
                        {elementType === 'trigger' ? t('action.deleteTrigger') : t('action.deleteAction')}
                    </button>
                </div>
            )}
        </div>
    );
};

export default ActionEditor;
