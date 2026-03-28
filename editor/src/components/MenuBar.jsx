import React, { useState, useEffect, useRef } from 'react';
import { useLocale } from '../i18n';

const MenuBar = ({
    onNewStory,
    onSaveStory,
    onLoadStory,
    stories,
    currentStoryId,
    onUndo,
    onRedo,
    canUndo,
    canRedo,
    viewMode,
    onViewModeChange,
    onAnalyzeStory,
    unsavedCount = 0,
    onShowVersionHistory,
    graphStatus,
    onCompileGraph,
    graphCompileLoading = false,
}) => {
    const [activeMenu, setActiveMenu] = useState(null);
    const menuRef = useRef(null);
    const { locale, locales, setLocale, t } = useLocale();

    useEffect(() => {
        const handleClickOutside = (event) => {
            if (menuRef.current && !menuRef.current.contains(event.target)) {
                setActiveMenu(null);
            }
        };

        document.addEventListener('mousedown', handleClickOutside);
        return () => {
            document.removeEventListener('mousedown', handleClickOutside);
        };
    }, []);

    const handleMenuClick = (menuName) => {
        setActiveMenu(activeMenu === menuName ? null : menuName);
    };

    const handleMenuItemClick = (action, ...args) => {
        action(...args);
        setActiveMenu(null);
    };

    const graphButtonTitle = graphStatus?.status === 'current'
        ? t('menu.graph.currentTitle')
        : graphStatus?.status === 'stale'
            ? t('menu.graph.staleTitle')
            : t('menu.graph.missingTitle');

    const graphButtonLabel = graphCompileLoading
        ? t('menu.graph.compiling')
        : graphStatus?.status === 'current'
            ? t('menu.graph.current')
            : graphStatus?.status === 'stale'
                ? t('menu.graph.stale')
                : t('menu.graph.missing');

    return (
        <div className="menu-bar" ref={menuRef}>
            <div className="menu-item">
                <div
                    className={`menu-label ${activeMenu === 'file' ? 'active' : ''}`}
                    onClick={() => handleMenuClick('file')}
                >
                    {t('menu.file')}
                </div>
                {activeMenu === 'file' && (
                    <div className="dropdown-menu">
                        <div className="dropdown-item" onClick={() => handleMenuItemClick(onNewStory)}>
                            {t('menu.newStory')}
                        </div>
                        <div className="dropdown-item" onClick={() => handleMenuItemClick(onSaveStory)}>
                            {t('menu.saveStory')}
                        </div>
                        <div className="dropdown-separator"></div>
                        <div className="dropdown-item" onClick={() => handleMenuItemClick(onAnalyzeStory)}>
                            {t('menu.analyzeStory')}
                        </div>
                        <div className="dropdown-separator"></div>
                        <div className="dropdown-item has-submenu">
                            {t('menu.loadStory')}
                            <div className="submenu-content">
                                {stories.map(story => (
                                    <div
                                        key={story.id}
                                        className={`dropdown-item ${currentStoryId === story.id ? 'selected' : ''}`}
                                        onClick={(e) => {
                                            e.stopPropagation();
                                            handleMenuItemClick(onLoadStory, story.id);
                                        }}
                                    >
                                        {story.title}
                                    </div>
                                ))}
                                {stories.length === 0 && (
                                    <div className="dropdown-item disabled">{t('menu.noStoriesFound')}</div>
                                )}
                            </div>
                        </div>
                        <div className="dropdown-item" onClick={() => handleMenuItemClick(onShowVersionHistory)}>
                            {t('menu.versionHistory')}
                        </div>
                    </div>
                )}
            </div>

            <div className="menu-item">
                <div
                    className={`menu-label ${activeMenu === 'edit' ? 'active' : ''}`}
                    onClick={() => handleMenuClick('edit')}
                >
                    {t('menu.edit')}
                </div>
                {activeMenu === 'edit' && (
                    <div className="dropdown-menu">
                        <div
                            className={`dropdown-item ${!canUndo ? 'disabled' : ''}`}
                            onClick={() => canUndo && handleMenuItemClick(onUndo)}
                        >
                            {t('menu.undo')} <span className="shortcut">Ctrl+Z</span>
                        </div>
                        <div
                            className={`dropdown-item ${!canRedo ? 'disabled' : ''}`}
                            onClick={() => canRedo && handleMenuItemClick(onRedo)}
                        >
                            {t('menu.redo')} <span className="shortcut">Ctrl+Y</span>
                        </div>
                    </div>
                )}
            </div>

            <div className="menu-item">
                <div
                    className={`menu-label ${activeMenu === 'view' ? 'active' : ''}`}
                    onClick={() => handleMenuClick('view')}
                >
                    {t('menu.view')}
                </div>
                {activeMenu === 'view' && (
                    <div className="dropdown-menu">
                        <div
                            className={`dropdown-item ${viewMode === 'default' ? 'selected' : ''}`}
                            onClick={() => handleMenuItemClick(onViewModeChange, 'default')}
                        >
                            {t('menu.simpleView')}
                        </div>
                        <div
                            className={`dropdown-item ${viewMode === 'detailed' ? 'selected' : ''}`}
                            onClick={() => handleMenuItemClick(onViewModeChange, 'detailed')}
                        >
                            {t('menu.detailedView')}
                        </div>
                    </div>
                )}
            </div>

            <div className="menu-item">
                <label className="menu-label" htmlFor="editor-language-selector">
                    {t('locale.label')}
                </label>
                <select
                    id="editor-language-selector"
                    className="menu-language-select"
                    value={locale}
                    onChange={(event) => setLocale(event.target.value)}
                >
                    {locales.map((localeOption) => (
                        <option key={localeOption} value={localeOption}>
                            {t(`locale.${localeOption}`)}
                        </option>
                    ))}
                </select>
            </div>

            {unsavedCount > 0 && (
                <div className="unsaved-indicator">
                    <span className="unsaved-dot"></span>
                    <span className="unsaved-text">{t('menu.unsaved', { count: unsavedCount })}</span>
                </div>
            )}

            {graphStatus && (
                <button
                    type="button"
                    className={`graph-status-button ${graphStatus.status || 'missing'}`}
                    onClick={onCompileGraph}
                    disabled={graphCompileLoading || !onCompileGraph || graphStatus.status === 'current'}
                    title={graphButtonTitle}
                >
                    {graphButtonLabel}
                </button>
            )}
        </div>
    );
};

export default MenuBar;
