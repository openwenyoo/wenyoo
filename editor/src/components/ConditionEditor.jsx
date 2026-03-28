import React, { useState, useEffect } from 'react';
import { useLocale } from '../i18n';

const ConditionEditor = ({ condition = {}, onChange, onRemove }) => {
    const [type, setType] = useState(condition.type || '');
    const [details, setDetails] = useState(condition || {});
    const { t } = useLocale();

    // Sync state when condition prop changes
    useEffect(() => {
        setType(condition.type || '');
        setDetails(condition || {});
    }, [condition]);

    const handleTypeChange = (e) => {
        const newType = e.target.value;
        setType(newType);
        // Reset details when type changes, keeping only type
        onChange({ type: newType });
    };

    const handleDetailChange = (key, value) => {
        const updated = { ...details, [key]: value };
        setDetails(updated);
        onChange(updated);
    };

    const renderFields = () => {
        switch (type) {
            case 'inventory':
                return (
                    <div className="condition-fields">
                        <div className="form-group">
                            <label>{t('condition.operator')}</label>
                            <select 
                                value={details.operator || 'has'} 
                                onChange={(e) => handleDetailChange('operator', e.target.value)}
                            >
                                <option value="has">has</option>
                                <option value="not_has">not_has</option>
                            </select>
                        </div>
                        <div className="form-group">
                            <label>{t('condition.itemId')}</label>
                            <input
                                placeholder={t('condition.itemIdPlaceholder')}
                                value={details.value || ''}
                                onChange={(e) => handleDetailChange('value', e.target.value)}
                            />
                        </div>
                    </div>
                );
            case 'variable':
                return (
                    <div className="condition-fields">
                        <div className="form-group">
                            <label>{t('condition.variableName')}</label>
                            <input
                                placeholder={t('condition.variablePlaceholder')}
                                value={details.variable || ''}
                                onChange={(e) => handleDetailChange('variable', e.target.value)}
                            />
                        </div>
                        <div className="form-group">
                            <label>{t('condition.operator')}</label>
                            <select 
                                value={details.operator || 'eq'} 
                                onChange={(e) => handleDetailChange('operator', e.target.value)}
                            >
                                <option value="eq">== (equals)</option>
                                <option value="neq">!= (not equals)</option>
                                <option value="gt">&gt; (greater than)</option>
                                <option value="gte">&gt;= (greater or equal)</option>
                                <option value="lt">&lt; (less than)</option>
                                <option value="lte">&lt;= (less or equal)</option>
                            </select>
                        </div>
                        <div className="form-group">
                            <label>{t('condition.value')}</label>
                            <input
                                placeholder={t('condition.valuePlaceholder')}
                                value={details.value ?? ''}
                                onChange={(e) => handleDetailChange('value', e.target.value)}
                            />
                        </div>
                    </div>
                );
            case 'object_status':
                return (
                    <div className="condition-fields">
                        <div className="form-group">
                            <label>{t('condition.targetObjectId')}</label>
                            <input
                                placeholder={t('condition.objectIdPlaceholder')}
                                value={details.target || ''}
                                onChange={(e) => handleDetailChange('target', e.target.value)}
                            />
                        </div>
                        <div className="form-group">
                            <label>{t('condition.status')}</label>
                            <input
                                placeholder={t('condition.statusPlaceholder')}
                                value={details.status || ''}
                                onChange={(e) => handleDetailChange('status', e.target.value)}
                            />
                        </div>
                    </div>
                );
            case 'script':
                return (
                    <div className="condition-fields">
                        <div className="form-group">
                            <label>{t('condition.luaScript')} <span className="field-hint">({t('condition.luaHint')})</span></label>
                            <textarea
                                className="script-textarea"
                                placeholder={t('condition.luaPlaceholder')}
                                value={details.script || ''}
                                onChange={(e) => handleDetailChange('script', e.target.value)}
                                rows={3}
                            />
                        </div>
                    </div>
                );
            default:
                return <p className="empty-state">{t('condition.selectPrompt')}</p>;
        }
    };

    return (
        <div className="list-item-editor condition-editor">
            <div className="sticky-sub-subsection-header">{t('condition.title')}</div>
            <div className="form-group">
                <label>{t('condition.type')}</label>
                <select value={type} onChange={handleTypeChange}>
                    <option value="">{t('condition.selectType')}</option>
                    <option value="variable">{t('condition.variable')}</option>
                    <option value="inventory">{t('condition.inventory')}</option>
                    <option value="object_status">{t('condition.objectStatus')}</option>
                    <option value="script">{t('condition.script')}</option>
                </select>
            </div>
            {renderFields()}
            <button className="remove-btn" onClick={onRemove}>{t('condition.remove')}</button>
        </div>
    );
};

export default ConditionEditor;
