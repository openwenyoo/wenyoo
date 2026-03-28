import React, { useMemo, useRef, useState } from 'react';
import './ImportWizard.css';
import { SUPPORTED_IMPORT_ACCEPT, buildImportDraftFromFile } from '../services/importService';
import { prepareImportConversion } from '../services/aiService';
import { useLocale } from '../i18n';

const getSourceLabel = (importDraft, t) => {
    if (!importDraft) return '';

    switch (importDraft.sourceType) {
        case 'character_card':
            return t('import.source.character_card');
        case 'markdown':
            return t('import.source.markdown');
        case 'text':
            return t('import.source.text');
        default:
            return importDraft.sourceType || t('import.source.default');
    }
};

const ImportWizard = ({
    isOpen,
    onClose,
    onConversionReady,
}) => {
    const { t } = useLocale();
    const fileInputRef = useRef(null);
    const [selectedFileName, setSelectedFileName] = useState('');
    const [importDraft, setImportDraft] = useState(null);
    const [writerIntent, setWriterIntent] = useState('');
    const [isParsing, setIsParsing] = useState(false);
    const [isGenerating, setIsGenerating] = useState(false);
    const [error, setError] = useState('');

    const sourceLabel = useMemo(() => getSourceLabel(importDraft, t), [importDraft, t]);

    if (!isOpen) return null;

    const resetState = () => {
        setSelectedFileName('');
        setImportDraft(null);
        setWriterIntent('');
        setIsParsing(false);
        setIsGenerating(false);
        setError('');
        if (fileInputRef.current) {
            fileInputRef.current.value = '';
        }
    };

    const handleClose = () => {
        resetState();
        onClose?.();
    };

    const handleFileSelected = async (event) => {
        const file = event.target.files?.[0];
        if (!file) return;

        setSelectedFileName(file.name);
        setImportDraft(null);
        setError('');
        setIsParsing(true);

        try {
            const draft = await buildImportDraftFromFile(file);
            setImportDraft(draft);

            if (!writerIntent.trim()) {
                setWriterIntent(t('import.defaultIntent', { sourceType: getSourceLabel(draft, t).toLowerCase() }));
            }
        } catch (err) {
            setError(err.message || t('import.failParse'));
        } finally {
            setIsParsing(false);
        }
    };

    const handleGenerate = async () => {
        if (!importDraft || !writerIntent.trim()) return;

        setIsGenerating(true);
        setError('');

        try {
            const result = await prepareImportConversion(importDraft, writerIntent.trim());
            onConversionReady?.({
                importDraft,
                writerIntent: writerIntent.trim(),
                detailedOutline: result.detailedOutline,
                plan: result.plan
            });
        } catch (err) {
            setError(err.message || t('import.failPrepare'));
        } finally {
            setIsGenerating(false);
        }
    };

    return (
        <div className="import-wizard-overlay" onClick={handleClose}>
            <div className="import-wizard-panel" onClick={(event) => event.stopPropagation()}>
                <div className="import-wizard-header">
                    <div>
                        <h2>{t('import.title')}</h2>
                        <p>{t('import.subtitle')}</p>
                    </div>
                    <button className="import-wizard-close" onClick={handleClose}>×</button>
                </div>

                <div className="import-wizard-body">
                    {error && (
                        <div className="import-wizard-error">
                            <strong>{t('import.errorPrefix')}</strong> {error}
                        </div>
                    )}

                    <div className="import-upload-box">
                        <label htmlFor="import-source-file">{t('import.sourceFile')}</label>
                        <input
                            ref={fileInputRef}
                            id="import-source-file"
                            type="file"
                            accept={SUPPORTED_IMPORT_ACCEPT}
                            onChange={handleFileSelected}
                            disabled={isParsing || isGenerating}
                        />
                        <p className="import-upload-hint">
                            {t('import.supported')}
                        </p>
                        {selectedFileName && (
                            <div className="import-selected-file">
                                <span>{selectedFileName}</span>
                                {isParsing && <span className="import-status-badge">{t('import.parsing')}</span>}
                            </div>
                        )}
                    </div>

                    {importDraft && (
                        <div className="import-review-grid">
                            <div className="import-review-card">
                                <div className="import-review-meta">
                                    <span className="import-source-chip">{sourceLabel}</span>
                                    <span className="import-source-chip secondary">{importDraft.sourceFormat}</span>
                                </div>
                                <h3>{importDraft.title}</h3>
                                <p>{importDraft.summary || t('import.noSummary')}</p>
                                <div className="import-stat-row">
                                    <span>{t('import.stats.characters', { count: importDraft.characters?.length || 0 })}</span>
                                    <span>{t('import.stats.loreEntries', { count: importDraft.worldInfo?.length || 0 })}</span>
                                    <span>{t('import.stats.warnings', { count: importDraft.importWarnings?.length || 0 })}</span>
                                </div>
                            </div>

                            <div className="import-review-card">
                                <h4>{t('import.extractedHighlights')}</h4>
                                {importDraft.characters?.length > 0 ? (
                                    <ul className="import-simple-list">
                                        {importDraft.characters.slice(0, 3).map((character) => (
                                            <li key={character.id || character.name}>
                                                <strong>{character.name || character.id}</strong>
                                                <span>{character.description || character.personality || character.scenario || t('import.noSummary')}</span>
                                            </li>
                                        ))}
                                    </ul>
                                ) : (
                                    <p className="import-muted">{t('import.noCharacters')}</p>
                                )}
                            </div>

                            <div className="import-review-card wide">
                                <h4>{t('import.sourceContext')}</h4>
                                <div className="import-source-preview">
                                    {importDraft.rawText || t('import.noRawText')}
                                </div>
                            </div>

                            {importDraft.importWarnings?.length > 0 && (
                                <div className="import-review-card wide warning">
                                    <h4>{t('import.warnings')}</h4>
                                    <ul className="import-simple-list">
                                        {importDraft.importWarnings.map((warning, index) => (
                                            <li key={`${warning}-${index}`}>
                                                <span>{warning}</span>
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                            )}
                        </div>
                    )}

                    {importDraft && (
                        <div className="import-intent-section">
                            <label htmlFor="writer-intent">{t('import.intentLabel')}</label>
                            <textarea
                                id="writer-intent"
                                value={writerIntent}
                                onChange={(event) => setWriterIntent(event.target.value)}
                                placeholder={t('import.intentPlaceholder')}
                                rows={5}
                                disabled={isGenerating}
                            />
                        </div>
                    )}
                </div>

                <div className="import-wizard-actions">
                    <button className="import-btn secondary" onClick={handleClose} disabled={isParsing || isGenerating}>
                        {t('generic.cancel')}
                    </button>
                    <button
                        className="import-btn primary"
                        onClick={handleGenerate}
                        disabled={!importDraft || !writerIntent.trim() || isParsing || isGenerating}
                    >
                        {isGenerating ? t('import.preparing') : t('import.prepare')}
                    </button>
                </div>
            </div>
        </div>
    );
};

export default ImportWizard;
