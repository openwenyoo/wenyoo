import React, { useState } from 'react';
import '../styles/ai-assistant.css';
import { useLocale } from '../i18n';

const AIAssistant = ({
    isOpen,
    onClose,
    contextInfo,
    onGenerate,
    title,
    placeholder,
    selectedItemsCount = 0,
    selectedItemsNames = [],
    // External loading state (for streaming AI)
    externalLoading = false,
    externalMessage = ''
}) => {
    const [prompt, setPrompt] = useState('');
    const [internalLoading, setInternalLoading] = useState(false);
    const { t } = useLocale();
    
    // Use external loading if provided, otherwise use internal
    const isLoading = externalLoading || internalLoading;
    const loadingMessage = externalMessage || t('assistant.processing');

    if (!isOpen) return null;

    const handleSubmit = async () => {
        if (!prompt.trim()) return;
        
        // If external loading is used, just call onGenerate and let parent handle state
        if (externalLoading !== undefined && externalMessage !== undefined) {
            try {
                await onGenerate(prompt);
                setPrompt('');
            } catch (error) {
                console.error("AI Error:", error);
            }
            return;
        }
        
        // Otherwise use internal loading state
        setInternalLoading(true);
        try {
            await onGenerate(prompt);
            setPrompt('');
        } catch (error) {
            console.error("AI Error:", error);
            alert(t('assistant.error', { error: error.message }));
        } finally {
            setInternalLoading(false);
        }
    };

    return (
        <div className="ai-assistant-panel" style={{
            position: 'absolute',
            top: '40px',
            right: '10px',
            zIndex: 2000,
            boxShadow: 'var(--shadow-hard)'
        }}>
            <div className="ai-header">
                <span>{title || t('assistant.defaultTitle')}</span>
                <button className="ai-close-btn" onClick={onClose}>×</button>
            </div>
            <div className="ai-content">
                {contextInfo && (
                    <div className="ai-context-info">
                        <p>{contextInfo}</p>
                    </div>
                )}
                {selectedItemsCount > 0 && (
                    <div className="selected-nodes-info">
                        <span className="selected-nodes-count">{t('assistant.selectedCount', { count: selectedItemsCount })}</span>
                        <span>{selectedItemsNames.join(', ')}</span>
                    </div>
                )}
                
                {/* Show thinking indicator when loading */}
                {isLoading && (
                    <div className="ai-thinking-indicator">
                        <div className="ai-thinking-spinner"></div>
                        <span className="ai-thinking-text">{loadingMessage}</span>
                    </div>
                )}
                
                <textarea
                    value={prompt}
                    onChange={(e) => setPrompt(e.target.value)}
                    placeholder={placeholder || t('assistant.defaultPlaceholder')}
                    autoFocus
                    disabled={isLoading}
                    onKeyDown={(e) => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                            e.preventDefault();
                            handleSubmit();
                        }
                    }}
                />
                <button
                    className={`ai-submit-btn ${isLoading ? 'loading' : ''}`}
                    onClick={handleSubmit}
                    disabled={isLoading || !prompt}
                >
                    {isLoading ? loadingMessage : t('assistant.submit')}
                </button>
            </div>
        </div>
    );
};

export default AIAssistant;
