import React, { useState, useEffect } from 'react';
import { useLocale } from '../i18n';

const EFFECT_TYPES = [
    { value: 'display_text', label: 'Display Text', category: 'narrative' },
    { value: 'goto_node', label: 'Go to Node', category: 'navigation' },
    { value: 'set_variable', label: 'Set Variable', category: 'state' },
    { value: 'calculate', label: 'Calculate', category: 'state' },
    { value: 'add_to_inventory', label: 'Add to Inventory', category: 'inventory' },
    { value: 'remove_from_inventory', label: 'Remove from Inventory', category: 'inventory' },
    { value: 'update_object_status', label: 'Update Object Status', category: 'state' },
    { value: 'set_node_description', label: 'Set Node Description', category: 'narrative' },
    { value: 'set_object_explicit_state', label: 'Set Object Explicit State', category: 'narrative' },
    { value: 'move_to_node', label: 'Move Character to Node', category: 'navigation' },
    { value: 'random_number', label: 'Random Number', category: 'utility' },
    { value: 'dice_roll', label: 'Dice Roll', category: 'utility' },
    { value: 'show_form', label: 'Show Form', category: 'ui' },
    { value: 'script', label: 'Script (Lua)', category: 'advanced' },
    { value: 'call_function', label: 'Call Function', category: 'advanced' },
];

const CATEGORY_COLORS = {
    narrative: '#2196f3',
    navigation: '#ff9800',
    state: '#4caf50',
    inventory: '#9c27b0',
    utility: '#607d8b',
    ui: '#00bcd4',
    advanced: '#795548',
};

const EffectFields = ({ effect, onChange, t }) => {
    const handleChange = (key, value) => {
        onChange({ ...effect, [key]: value });
    };

    switch (effect.type) {
        case 'display_text':
            return (
                <div className="effect-fields">
                    <textarea
                        value={effect.text || ''}
                        onChange={(e) => handleChange('text', e.target.value)}
                        placeholder={t('effect.textPlaceholder')}
                        rows={2}
                    />
                    <input
                        value={effect.speaker || ''}
                        onChange={(e) => handleChange('speaker', e.target.value)}
                        placeholder={t('effect.speakerPlaceholder')}
                    />
                </div>
            );
        case 'goto_node':
        case 'move_to_node':
            return (
                <div className="effect-fields">
                    <input
                        value={effect.target || ''}
                        onChange={(e) => handleChange('target', e.target.value)}
                        placeholder={t('effect.targetNodePlaceholder')}
                    />
                    {effect.type === 'goto_node' && (
                        <input
                            value={effect.text || ''}
                            onChange={(e) => handleChange('text', e.target.value)}
                            placeholder={t('effect.linkTextPlaceholder')}
                        />
                    )}
                </div>
            );
        case 'set_variable':
            return (
                <div className="effect-fields">
                    <input
                        value={effect.target || ''}
                        onChange={(e) => handleChange('target', e.target.value)}
                        placeholder={t('effect.variableNamePlaceholder')}
                    />
                    <input
                        value={effect.value ?? ''}
                        onChange={(e) => handleChange('value', e.target.value)}
                        placeholder={t('condition.value')}
                    />
                </div>
            );
        case 'calculate':
            return (
                <div className="effect-fields">
                    <input
                        value={effect.target || ''}
                        onChange={(e) => handleChange('target', e.target.value)}
                        placeholder={t('effect.targetVariablePlaceholder')}
                    />
                    <input
                        value={effect.left || ''}
                        onChange={(e) => handleChange('left', e.target.value)}
                        placeholder={t('effect.leftOperandPlaceholder')}
                    />
                    <select
                        value={effect.operator || 'add'}
                        onChange={(e) => handleChange('operator', e.target.value)}
                    >
                        <option value="add">+ Add</option>
                        <option value="subtract">- Subtract</option>
                        <option value="multiply">* Multiply</option>
                        <option value="divide">/ Divide</option>
                    </select>
                    <input
                        value={effect.right || ''}
                        onChange={(e) => handleChange('right', e.target.value)}
                        placeholder={t('effect.rightOperandPlaceholder')}
                    />
                </div>
            );
        case 'add_to_inventory':
        case 'remove_from_inventory':
            return (
                <div className="effect-fields">
                    <input
                        value={effect.value || ''}
                        onChange={(e) => handleChange('value', e.target.value)}
                        placeholder={t('condition.itemId')}
                    />
                </div>
            );
        case 'update_object_status':
            return (
                <div className="effect-fields">
                    <input
                        value={effect.target || ''}
                        onChange={(e) => handleChange('target', e.target.value)}
                        placeholder={t('effect.objectIdPlaceholder')}
                    />
                    <input
                        value={effect.value || ''}
                        onChange={(e) => handleChange('value', e.target.value)}
                        placeholder={t('effect.newStatusPlaceholder')}
                    />
                </div>
            );
        case 'set_node_description':
        case 'set_object_explicit_state':
            return (
                <div className="effect-fields">
                    <input
                        value={effect.target || ''}
                        onChange={(e) => handleChange('target', e.target.value)}
                        placeholder={t('effect.targetIdPlaceholder')}
                    />
                    <textarea
                        value={effect.text || effect.value || ''}
                        onChange={(e) => handleChange('text', e.target.value)}
                        placeholder={t('effect.newDescriptionPlaceholder')}
                        rows={2}
                    />
                </div>
            );
        case 'random_number':
            return (
                <div className="effect-fields">
                    <input
                        value={effect.target || ''}
                        onChange={(e) => handleChange('target', e.target.value)}
                        placeholder={t('effect.storeToVariablePlaceholder')}
                    />
                    <div className="effect-fields-row">
                        <input
                            type="number"
                            value={effect.min ?? 1}
                            onChange={(e) => handleChange('min', parseInt(e.target.value) || 0)}
                            placeholder={t('effect.min')}
                        />
                        <span>{t('effect.to')}</span>
                        <input
                            type="number"
                            value={effect.max ?? 6}
                            onChange={(e) => handleChange('max', parseInt(e.target.value) || 0)}
                            placeholder={t('effect.max')}
                        />
                    </div>
                </div>
            );
        case 'dice_roll':
            return (
                <div className="effect-fields">
                    <input
                        value={effect.target || ''}
                        onChange={(e) => handleChange('target', e.target.value)}
                        placeholder={t('effect.storeResultPlaceholder')}
                    />
                    <input
                        value={effect.dice || ''}
                        onChange={(e) => handleChange('dice', e.target.value)}
                        placeholder={t('effect.dicePlaceholder')}
                    />
                </div>
            );
        case 'show_form':
            return (
                <div className="effect-fields">
                    <input
                        value={effect.value || ''}
                        onChange={(e) => handleChange('value', e.target.value)}
                        placeholder={t('effect.formIdPlaceholder')}
                    />
                </div>
            );
        case 'script':
            return (
                <div className="effect-fields">
                    <textarea
                        className="script-textarea"
                        value={effect.script || ''}
                        onChange={(e) => handleChange('script', e.target.value)}
                        placeholder={t('effect.luaPlaceholder')}
                        rows={3}
                    />
                </div>
            );
        case 'call_function':
            return (
                <div className="effect-fields">
                    <input
                        value={effect.target || ''}
                        onChange={(e) => handleChange('target', e.target.value)}
                        placeholder={t('effect.functionIdPlaceholder')}
                    />
                </div>
            );
        default:
            return (
                <div className="effect-fields">
                    <textarea
                        value={JSON.stringify(effect, null, 2)}
                        onChange={(e) => {
                            try {
                                const parsed = JSON.parse(e.target.value);
                                onChange(parsed);
                            } catch {}
                        }}
                        placeholder={t('effect.rawJsonPlaceholder')}
                        rows={3}
                        className="script-textarea"
                    />
                </div>
            );
    }
};

const EffectListEditor = ({ effects = [], onChange }) => {
    const [expandedIndex, setExpandedIndex] = useState(null);
    const { t } = useLocale();

    const addEffect = (type = '') => {
        const newEffect = { type };
        const newEffects = [...effects, newEffect];
        onChange(newEffects);
        setExpandedIndex(newEffects.length - 1);
    };

    const updateEffect = (index, updated) => {
        const newEffects = [...effects];
        newEffects[index] = updated;
        onChange(newEffects);
    };

    const removeEffect = (index) => {
        onChange(effects.filter((_, i) => i !== index));
        if (expandedIndex === index) setExpandedIndex(null);
        else if (expandedIndex > index) setExpandedIndex(expandedIndex - 1);
    };

    const moveEffect = (index, direction) => {
        const newIndex = index + direction;
        if (newIndex < 0 || newIndex >= effects.length) return;
        const newEffects = [...effects];
        [newEffects[index], newEffects[newIndex]] = [newEffects[newIndex], newEffects[index]];
        onChange(newEffects);
        setExpandedIndex(newIndex);
    };

    const getEffectLabel = (effect) => {
        const typeDef = EFFECT_TYPES.find((item) => item.value === effect.type);
        return typeDef ? t(`effect.${typeDef.value}`) : (effect.type || t('effect.unknown'));
    };

    const getEffectColor = (effect) => {
        const typeDef = EFFECT_TYPES.find(t => t.value === effect.type);
        return CATEGORY_COLORS[typeDef?.category] || '#999';
    };

    const getEffectSummary = (effect) => {
        switch (effect.type) {
            case 'display_text': return effect.text ? `"${effect.text.substring(0, 40)}..."` : '';
            case 'goto_node': return effect.target || '';
            case 'set_variable': return `${effect.target || '?'} = ${effect.value ?? '?'}`;
            case 'add_to_inventory': return effect.value || '';
            case 'remove_from_inventory': return effect.value || '';
            case 'update_object_status': return `${effect.target || '?'} → ${effect.value || '?'}`;
            case 'calculate': return `${effect.target || '?'} = ${effect.left || '?'} ${effect.operator || '+'} ${effect.right || '?'}`;
            case 'dice_roll': return effect.dice || '';
            case 'script': return t('effect.luaScript');
            case 'call_function': return effect.target || '';
            default: return '';
        }
    };

    return (
        <div className="effect-list-editor">
            {effects.length > 0 ? (
                <div className="effect-items">
                    {effects.map((effect, index) => (
                        <div key={index} className={`effect-item ${expandedIndex === index ? 'expanded' : ''}`}>
                            <div
                                className="effect-item-header"
                                onClick={() => setExpandedIndex(expandedIndex === index ? null : index)}
                            >
                                <span
                                    className="effect-type-dot"
                                    style={{ background: getEffectColor(effect) }}
                                />
                                <span className="effect-type-label">{getEffectLabel(effect)}</span>
                                <span className="effect-summary">{getEffectSummary(effect)}</span>
                                <div className="effect-item-actions">
                                    <button
                                        className="effect-move-btn"
                                        onClick={(e) => { e.stopPropagation(); moveEffect(index, -1); }}
                                        disabled={index === 0}
                                        title={t('effect.moveUp')}
                                    >↑</button>
                                    <button
                                        className="effect-move-btn"
                                        onClick={(e) => { e.stopPropagation(); moveEffect(index, 1); }}
                                        disabled={index === effects.length - 1}
                                        title={t('effect.moveDown')}
                                    >↓</button>
                                    <button
                                        className="effect-remove-btn"
                                        onClick={(e) => { e.stopPropagation(); removeEffect(index); }}
                                        title={t('effect.remove')}
                                    >×</button>
                                </div>
                            </div>
                            {expandedIndex === index && (
                                <div className="effect-item-body">
                                    <div className="form-group">
                                        <label>{t('effect.type')}</label>
                                        <select
                                            value={effect.type || ''}
                                            onChange={(e) => updateEffect(index, { type: e.target.value })}
                                        >
                                            <option value="">{t('effect.selectType')}</option>
                                            {EFFECT_TYPES.map((effectType) => (
                                                <option key={effectType.value} value={effectType.value}>{t(`effect.${effectType.value}`)}</option>
                                            ))}
                                        </select>
                                    </div>
                                    {effect.type && (
                                        <EffectFields
                                            effect={effect}
                                            t={t}
                                            onChange={(updated) => updateEffect(index, updated)}
                                        />
                                    )}
                                </div>
                            )}
                        </div>
                    ))}
                </div>
            ) : (
                <div className="empty-state">{t('effect.none')}</div>
            )}
            <button className="add-button" onClick={() => addEffect()} title={t('effect.add')}>
                {t('effect.add')}
            </button>
        </div>
    );
};

export default EffectListEditor;
