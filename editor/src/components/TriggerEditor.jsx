import React, { useState, useEffect } from 'react';
import ConditionEditor from './ConditionEditor';
import EffectListEditor from './EffectListEditor';
import { useLocale } from '../i18n';

const TriggerEditor = ({ trigger = {}, onChange, onRemove, elementType = 'trigger' }) => {
    const { t } = useLocale();
    const [id, setId] = useState(trigger.id || '');
    const [name, setName] = useState(trigger.name || '');
    const [triggerType, setTriggerType] = useState(trigger.type || '');
    const [intent, setIntent] = useState(trigger.intent || '');
    const [conditions, setConditions] = useState(trigger.conditions || []);
    const [effects, setEffects] = useState(trigger.effects || []);

    useEffect(() => {
        setId(trigger.id || '');
        setName(trigger.name || '');
        setTriggerType(trigger.type || '');
        setIntent(trigger.intent || '');
        setConditions(trigger.conditions || []);
        setEffects(trigger.effects || []);
    }, [trigger]);

    const updateParent = (updates) => {
        onChange({
            ...trigger,
            id: updates.id !== undefined ? updates.id : id,
            name: updates.name !== undefined ? updates.name : name,
            type: updates.type !== undefined ? updates.type : triggerType,
            intent: updates.intent !== undefined ? updates.intent : intent,
            conditions: updates.conditions !== undefined ? updates.conditions : conditions,
            effects: updates.effects !== undefined ? updates.effects : effects,
        });
    };

    const handleFieldChange = (field, value) => {
        if (field === 'id') setId(value);
        if (field === 'name') setName(value);
        if (field === 'type') setTriggerType(value);
        if (field === 'intent') setIntent(value);
        updateParent({ [field]: value });
    };

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

    const isLifecycleTrigger = ['pre_enter', 'post_enter', 'pre_leave', 'post_leave'].includes(triggerType);

    const [showConditions, setShowConditions] = useState(conditions.length > 0);
    const [showEffects, setShowEffects] = useState(true);

    return (
        <div className="secondary-editor-content">
            <div className={`sticky-section-header type-${elementType}`}>{t('trigger.details')}</div>

            <div className="form-row two-col">
                <div className="form-group">
                    <label>{t('node.id')}</label>
                    <input
                        value={id}
                        onChange={(e) => handleFieldChange('id', e.target.value)}
                    />
                </div>
                <div className="form-group">
                    <label>{t('node.name')}</label>
                    <input
                        value={name}
                        onChange={(e) => handleFieldChange('name', e.target.value)}
                        placeholder={t('trigger.namePlaceholder')}
                    />
                </div>
            </div>

            <div className="form-group">
                <label>{t('trigger.type')} <span className="field-hint">({t('trigger.typeHint')})</span></label>
                <select
                    value={triggerType}
                    onChange={(e) => handleFieldChange('type', e.target.value)}
                >
                    <option value="">{t('trigger.conditionBased')}</option>
                    <option value="pre_enter">pre_enter</option>
                    <option value="post_enter">post_enter</option>
                    <option value="pre_leave">pre_leave</option>
                    <option value="post_leave">post_leave</option>
                </select>
            </div>

            <div className="form-group">
                <label>{t('action.intent')} <span className="field-hint">({t('action.intentHint')})</span></label>
                <textarea
                    className="notebook-textarea"
                    value={intent}
                    onChange={(e) => handleFieldChange('intent', e.target.value)}
                    rows={4}
                    placeholder={t('action.intentPlaceholder')}
                />
            </div>

            {isLifecycleTrigger && (
                <div className="info-box" style={{
                    padding: '8px 12px',
                    background: 'var(--color-info-bg, #e3f2fd)',
                    borderRadius: 0,
                    marginBottom: 12,
                    fontSize: '0.85rem',
                    border: '1px solid var(--color-border)'
                }}>
                    {t('trigger.lifecycleInfo')}
                </div>
            )}

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
                        {conditions.map((cond, index) => (
                            <ConditionEditor
                                key={index}
                                condition={cond}
                                onChange={(updated) => updateCondition(index, updated)}
                                onRemove={() => removeCondition(index)}
                            />
                        ))}
                        {conditions.length === 0 && <div className="empty-state">{t('trigger.noConditions')}</div>}
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

            <button className="remove-btn" onClick={onRemove} style={{ marginTop: 20 }}>{t('trigger.remove')}</button>
        </div>
    );
};

export default TriggerEditor;
