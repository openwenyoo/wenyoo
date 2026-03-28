import React, { useState, useEffect } from 'react';
import PropertiesEditor from './PropertiesEditor';
import { useLocale } from '../i18n';

const ObjectEditor = ({ object = {}, onChange, onRemove, elementType = 'object' }) => {
    const { t } = useLocale();
    const [id, setId] = useState(object.id || '');
    const [name, setName] = useState(object.name || '');
    // DSPP model fields
    const [definition, setDefinition] = useState(object.definition || '');
    const [explicit_state, setExplicitState] = useState(object.explicit_state || '');
    const [implicit_state, setImplicitState] = useState(object.implicit_state || '');
    const [properties, setProperties] = useState(object.properties || {});

    const [showImplicitState, setShowImplicitState] = useState(false);
    const [showProperties, setShowProperties] = useState(false);

    // Sync state when object prop changes
    useEffect(() => {
        setId(object.id || '');
        setName(object.name || '');
        setDefinition(object.definition || '');
        setExplicitState(object.explicit_state || '');
        setImplicitState(object.implicit_state || '');
        setProperties(object.properties || {});
    }, [object]);

    const handleSave = () => {
        onChange({ id, name, definition, explicit_state, implicit_state, properties });
    };

    return (
        <div className="secondary-editor-content">
            <div className={`sticky-section-header type-${elementType}`}>{t('object.details')}</div>
            <div className="form-row two-col">
                <div className="form-group">
                    <label>{t('node.id')}</label>
                    <input value={id} onChange={(e) => setId(e.target.value)} onBlur={handleSave} />
                </div>
                <div className="form-group">
                    <label>{t('node.name')}</label>
                    <input value={name} onChange={(e) => setName(e.target.value)} onBlur={handleSave} />
                </div>
            </div>
            {/* DSPP Model Fields */}
            <div className="form-group">
                <label>{t('node.definition')} <span className="field-hint">({t('object.definitionHint')})</span></label>
                <textarea
                    className="notebook-textarea"
                    value={definition}
                    onChange={(e) => setDefinition(e.target.value)}
                    onBlur={handleSave}
                    rows={3}
                    placeholder={t('object.definitionPlaceholder')}
                />
            </div>

            <div className="form-group">
                <label>{t('node.explicitState')} <span className="field-hint">({t('object.explicitStateHint')})</span></label>
                <textarea
                    className="notebook-textarea"
                    value={explicit_state}
                    onChange={(e) => setExplicitState(e.target.value)}
                    onBlur={handleSave}
                    rows={2}
                    placeholder={t('object.explicitStatePlaceholder')}
                />
            </div>

            <div className="section collapsible-section">
                <div 
                    className="section-header clickable"
                    onClick={() => setShowImplicitState(!showImplicitState)}
                >
                    <h4>
                        <span className="collapse-indicator">{showImplicitState ? '▼' : '▶'}</span>
                        {t('object.implicitState')} <span className="field-hint">({t('object.implicitMeaningHint')})</span>
                    </h4>
                </div>
                {showImplicitState && (
                    <div className="form-group">
                        <textarea
                            className="notebook-textarea"
                            value={implicit_state}
                            onChange={(e) => setImplicitState(e.target.value)}
                            onBlur={handleSave}
                            rows={2}
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
                        {t('object.properties')} <span className="field-hint">({t('object.propertiesStatusHint')})</span>
                    </h4>
                </div>
                {showProperties && (
                    <PropertiesEditor
                        properties={properties}
                        onChange={(newProps) => {
                            setProperties(newProps);
                            onChange({ id, name, definition, explicit_state, implicit_state, properties: newProps });
                        }}
                    />
                )}
            </div>

            <button className="remove-btn" onClick={onRemove}>{t('object.remove')}</button>
        </div>
    );
};

export default ObjectEditor;
