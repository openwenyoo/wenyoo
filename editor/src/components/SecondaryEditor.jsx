import React, { useState } from 'react';
import ObjectEditor from './ObjectEditor';
import ActionEditor from './ActionEditor';
import TriggerEditor from './TriggerEditor';
import AIAssistant from './AIAssistant';
import { generateWithAI } from '../services/aiService';
import { useLocale } from '../i18n';

const SecondaryEditor = ({ selectedShape, onUpdateShape, onClose, isOpen }) => {
    const [showAI, setShowAI] = useState(false);
    const [aiLoading, setAiLoading] = useState(false);
    const { t } = useLocale();

    if (!selectedShape) return null;
    const { shape, type } = selectedShape;

    const handleChange = (updated) => {
        onUpdateShape(updated, type);
    };

    const handleRemove = () => {
        // Optional: implement remove logic if needed
        onClose();
    };

    const handleAIRequest = async (prompt) => {
        setAiLoading(true);
        try {
            const contextData = shape;
            const result = await generateWithAI({
                prompt,
                systemPrompt: `You are an AI assistant editing a game ${type} in this AI native text based game engine.

Return JSON with the updated ${type} fields. Include only fields you want to change.

For actions, use this format:
{
  "id": "action_id",
  "text": "Action description (NOT 'name')",
  "intent": "Optional natural-language behavior interpreted by the Architect",
  "effects": [{"type": "display_text", "text": "Result"}]
}

For objects, use this format:
{
  "id": "object_id",
  "name": "Object Name",
  "definition": "Static description and interaction rules",
  "explicit_state": "What the player currently sees",
  "implicit_state": "Hidden AI-only state",
  "properties": {"status": []}
}

For triggers, use this format:
{
  "id": "trigger_id",
  "type": "pre_enter|post_enter|pre_leave|post_leave",
  "intent": "Optional natural-language behavior interpreted by the Architect",
  "conditions": [...],
  "effects": [...]
}

IMPORTANT: Return the updated fields directly, not wrapped in operations.`,
                contextData
            });

            if (result.success) {
                const data = result.data;
                // Handle various response formats
                let updates = data;
                
                // If wrapped in operations, extract first operation's data
                if (data.operations && Array.isArray(data.operations) && data.operations.length > 0) {
                    updates = data.operations[0].data || data.operations[0];
                }
                // If wrapped in data field
                else if (data.data) {
                    updates = data.data;
                }
                
                // Don't overwrite id if not provided
                if (!updates.id && shape.id) {
                    updates.id = shape.id;
                }
                
                handleChange({ ...shape, ...updates });
                setShowAI(false);
                alert(t('secondary.aiApplied'));
            }
        } catch (e) {
            alert(t('assistant.error', { error: e.message }));
        } finally {
            setAiLoading(false);
        }
    };

    // Get element name with fallback
    const elementName = shape.name || shape.text || shape.id || 'Unnamed';

    // Determine Theme Color fallback
    let themeColor = 'var(--color-dark)';
    if (type === 'object') themeColor = 'var(--color-primary)';
    if (type === 'action') themeColor = 'var(--color-secondary)';
    if (type === 'trigger') themeColor = 'var(--color-accent)';

    // Render appropriate editor based on type
    const renderEditor = () => {
        switch (type) {
            case 'object':
                return (
                    <ObjectEditor
                        object={shape}
                        onChange={handleChange}
                        onRemove={handleRemove}
                        elementType={type}
                    />
                );
            case 'action':
                return (
                    <ActionEditor
                        action={shape}
                        onChange={handleChange}
                        onRemove={handleRemove}
                        elementType={type}
                    />
                );
            case 'trigger':
                return (
                    <TriggerEditor
                        trigger={shape}
                        onChange={handleChange}
                        onRemove={handleRemove}
                        elementType={type}
                    />
                );
            default:
                return null;
        }
    };

    return (
        <>
            <div className={`secondary-editor ${isOpen ? 'open' : ''}`}>
                <div className="sticky-header">
                    <h3>{elementName}</h3>
                    <div style={{ display: 'flex', gap: '8px' }}>
                        <button
                            className="header-ai-btn"
                            onClick={() => setShowAI(!showAI)}
                            title={t('secondary.aiAssistTitle')}
                            style={{ color: themeColor }}
                        >
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                                <path d="M12 2L14.5 9.5L22 12L14.5 14.5L12 22L9.5 14.5L2 12L9.5 9.5L12 2Z" fill="currentColor" />
                            </svg>
                            AI
                        </button>
                        <button className="header-close-btn" onClick={onClose}>×</button>
                    </div>
                </div>
                <AIAssistant
                    isOpen={showAI}
                    onClose={() => !aiLoading && setShowAI(false)}
                    onGenerate={handleAIRequest}
                    contextInfo={t('secondary.aiContext', { type })}
                    title={t('secondary.aiTitle', { type: `${type.charAt(0).toUpperCase() + type.slice(1)}` })}
                    externalLoading={aiLoading}
                    externalMessage={t('secondary.processing')}
                />
                <div className="editor-scroll-content">
                    {renderEditor()}
                </div>
            </div>
        </>
    );
};

export default SecondaryEditor;