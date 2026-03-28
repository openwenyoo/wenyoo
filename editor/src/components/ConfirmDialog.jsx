import React from 'react';
import { useLocale } from '../i18n';

const ConfirmDialog = ({
    isOpen,
    title,
    message,
    onSaveAndContinue,
    onDontSave,
    onCancel
}) => {
    const { t } = useLocale();
    const resolvedTitle = title ?? t('dialog.unsavedTitle');
    const resolvedMessage = message ?? t('dialog.unsavedMessage');

    if (!isOpen) return null;

    return (
        <div className="confirm-dialog-overlay" onClick={onCancel}>
            <div className="confirm-dialog" onClick={e => e.stopPropagation()}>
                <div className="confirm-dialog-header">
                    <h3>{resolvedTitle}</h3>
                </div>
                <div className="confirm-dialog-content">
                    <p>{resolvedMessage}</p>
                </div>
                <div className="confirm-dialog-actions">
                    <button className="btn btn-primary" onClick={onSaveAndContinue}>
                        {t('dialog.saveAndContinue')}
                    </button>
                    <button className="btn btn-danger" onClick={onDontSave}>
                        {t('dialog.dontSave')}
                    </button>
                    <button className="btn btn-secondary" onClick={onCancel}>
                        {t('generic.cancel')}
                    </button>
                </div>
            </div>
        </div>
    );
};

export default ConfirmDialog;
