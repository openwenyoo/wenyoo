import React, { useState } from 'react';
import './LoadingPanel.css';
import InputDialog from './InputDialog';
import { useLocale } from '../i18n';

const LoadingPanel = ({ onCreateNew, onLoadStory, onOpenImport, stories }) => {
    const [showStoryList, setShowStoryList] = useState(false);
    const [searchTerm, setSearchTerm] = useState('');
    const [tooltip, setTooltip] = useState({ visible: false, text: '', x: 0, y: 0 });
    const [showInputDialog, setShowInputDialog] = useState(false);
    const { t } = useLocale();

    const filteredStories = stories.filter(story => {
        const term = searchTerm.toLowerCase();
        return (
            story.name?.toLowerCase().includes(term) ||
            story.title?.toLowerCase().includes(term) ||
            story.id?.toLowerCase().includes(term) ||
            story.author?.toLowerCase().includes(term)
        );
    });

    const handleCreateNew = () => {
        setShowInputDialog(true);
    };

    const handleInputConfirm = (title) => {
        setShowInputDialog(false);
        onCreateNew(title);
    };

    const handleInputCancel = () => {
        setShowInputDialog(false);
    };

    const handleLoadStory = (storyId) => {
        onLoadStory(storyId);
    };

    return (
        <div className="loading-panel-overlay">
            <div className="loading-panel">
                {/* Decorative elements */}
                <div className="panel-decoration decoration-top-left"></div>
                <div className="panel-decoration decoration-top-right"></div>
                <div className="panel-decoration decoration-bottom-left"></div>

                {/* Header */}
                <div className="panel-header-section">
                    <h1 className="panel-title">{t('app.title')}</h1>
                    <p className="panel-subtitle">{t('loading.subtitle')}</p>
                </div>

                {!showStoryList ? (
                    /* Main Options */
                    <div className="panel-options">
                        <button
                            className="option-card option-create"
                            onClick={handleCreateNew}
                        >
                            <div className="option-icon">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                    <line x1="12" y1="5" x2="12" y2="19"></line>
                                    <line x1="5" y1="12" x2="19" y2="12"></line>
                                </svg>
                            </div>
                            <div className="option-content">
                                <h3>{t('loading.createNew')}</h3>
                                <p>{t('loading.createNewHelp')}</p>
                            </div>
                        </button>

                        <button
                            className="option-card option-load"
                            onClick={() => setShowStoryList(true)}
                        >
                            <div className="option-icon">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                    <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"></path>
                                </svg>
                            </div>
                            <div className="option-content">
                                <h3>{t('loading.loadExisting')}</h3>
                                <p>{t('loading.loadExistingHelp')}</p>
                            </div>
                        </button>

                        <button
                            className="option-card option-convert"
                            onClick={onOpenImport}
                        >
                            <div className="option-icon">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                    <polyline points="16 3 21 3 21 8"></polyline>
                                    <line x1="4" y1="20" x2="21" y2="3"></line>
                                    <polyline points="21 16 21 21 16 21"></polyline>
                                    <line x1="15" y1="15" x2="21" y2="21"></line>
                                    <line x1="4" y1="4" x2="9" y2="9"></line>
                                </svg>
                            </div>
                            <div className="option-content">
                                <h3>{t('loading.importSource')}</h3>
                                <p>{t('loading.importSourceHelp')}</p>
                            </div>
                        </button>
                    </div>
                ) : (
                    /* Story List */
                    <div className="story-list-section">
                        <div className="story-list-header">
                            <button
                                className="back-button"
                                onClick={() => setShowStoryList(false)}
                            >
                                {t('loading.back')}
                            </button>
                            <h2>{t('loading.selectStory')}</h2>
                        </div>

                        <div className="search-box">
                            <input
                                type="text"
                                placeholder={t('loading.searchStories')}
                                value={searchTerm}
                                onChange={(e) => setSearchTerm(e.target.value)}
                            />
                        </div>

                        <div className="story-list">
                            {filteredStories.length === 0 ? (
                                <div className="empty-state">
                                    {stories.length === 0
                                        ? t('loading.noStoriesFound')
                                        : t('loading.noStoriesMatch')}
                                </div>
                            ) : (
                                filteredStories.map((story) => (
                                    <button
                                        key={story.id}
                                        className="story-item"
                                        onClick={() => handleLoadStory(story.id)}
                                        onMouseEnter={(e) => {
                                            const rect = e.currentTarget.getBoundingClientRect();
                                            setTooltip({
                                                visible: true,
                                                text: story.description || '',
                                                x: rect.right + 12,
                                                y: rect.top + rect.height / 2
                                            });
                                        }}
                                        onMouseLeave={() => setTooltip(prev => ({ ...prev, visible: false }))}
                                    >
                                        <div className="story-icon">
                                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                                <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path>
                                                <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"></path>
                                            </svg>
                                        </div>
                                        <div className="story-info">
                                            <span className="story-name">{story.name || story.title || story.id}</span>
                                            <span className="story-author">{story.author || t('loading.unknownAuthor')}</span>
                                        </div>
                                        <div className="story-arrow">→</div>
                                    </button>
                                ))
                            )}
                        </div>

                        {/* Fixed-position tooltip */}
                        {tooltip.visible && tooltip.text && tooltip.text !== 'No description available' && (
                            <div
                                className="story-tooltip"
                                style={{
                                    position: 'fixed',
                                    left: tooltip.x,
                                    top: tooltip.y,
                                    transform: 'translateY(-50%)'
                                }}
                            >
                                <div className="story-tooltip-arrow"></div>
                                {tooltip.text}
                            </div>
                        )}
                    </div>
                )}

                {/* Footer */}
                <div className="panel-footer">
                    <span className="version-tag">Wenyoo</span>
                </div>
            </div>

            <InputDialog
                isOpen={showInputDialog}
                title={t('loading.newStoryTitle')}
                message={t('loading.newStoryMessage')}
                placeholder={t('loading.newStoryPlaceholder')}
                confirmText={t('loading.create')}
                onConfirm={handleInputConfirm}
                onCancel={handleInputCancel}
            />
        </div>
    );
};

export default LoadingPanel;

