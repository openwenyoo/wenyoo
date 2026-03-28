import React, { useState, useEffect, useRef } from 'react';
import './InputDialog.css';
import { useLocale } from '../i18n';

/**
 * Themed Input Dialog - Replaces browser's native prompt()
 * Styled to match the Bauhaus theme of the editor
 */
const InputDialog = ({
    isOpen,
    title,
    message = "",
    placeholder = "",
    defaultValue = "",
    confirmText,
    cancelText,
    onConfirm,
    onCancel
}) => {
    const [value, setValue] = useState(defaultValue);
    const inputRef = useRef(null);
    const { t } = useLocale();
    const resolvedTitle = title ?? t('generic.enterValue');
    const resolvedConfirmText = confirmText ?? t('generic.confirm');
    const resolvedCancelText = cancelText ?? t('generic.cancel');

    // Reset value when dialog opens
    useEffect(() => {
        if (isOpen) {
            setValue(defaultValue);
            // Focus input after a short delay to ensure dialog is rendered
            setTimeout(() => {
                inputRef.current?.focus();
                inputRef.current?.select();
            }, 50);
        }
    }, [isOpen, defaultValue]);

    // Handle keyboard events
    const handleKeyDown = (e) => {
        if (e.key === 'Enter' && value.trim()) {
            onConfirm(value.trim());
        } else if (e.key === 'Escape') {
            onCancel();
        }
    };

    if (!isOpen) return null;

    return (
        <div className="input-dialog-overlay" onClick={onCancel}>
            <div className="input-dialog" onClick={e => e.stopPropagation()}>
                {/* Decorative elements */}
                <div className="dialog-decoration decoration-top"></div>
                <div className="dialog-decoration decoration-side"></div>
                
                <div className="input-dialog-header">
                    <h3>{resolvedTitle}</h3>
                </div>
                <div className="input-dialog-content">
                    {message && <p className="input-dialog-message">{message}</p>}
                    <input
                        ref={inputRef}
                        type="text"
                        value={value}
                        onChange={(e) => setValue(e.target.value)}
                        onKeyDown={handleKeyDown}
                        placeholder={placeholder}
                        className="input-dialog-input"
                    />
                </div>
                <div className="input-dialog-actions">
                    <button 
                        className="btn btn-primary" 
                        onClick={() => value.trim() && onConfirm(value.trim())}
                        disabled={!value.trim()}
                    >
                        {resolvedConfirmText}
                    </button>
                    <button className="btn btn-secondary" onClick={onCancel}>
                        {resolvedCancelText}
                    </button>
                </div>
            </div>
        </div>
    );
};

export default InputDialog;
