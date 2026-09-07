import React, { useState, useEffect } from 'react';
import { compareStories, getVersion } from '../services/storyService';
import { useLocale } from '../i18n';
import StoryChanges from './StoryChanges';
import '../styles/story-quality.css';

const VersionHistoryDialog = ({ isOpen, onClose, storyId, getVersions, onRestore, currentStory }) => {
    const { t } = useLocale();
    const [versions, setVersions] = useState([]);
    const [loading, setLoading] = useState(false);
    const [restoring, setRestoring] = useState(false);
    const [error, setError] = useState('');
    const [selected, setSelected] = useState('');
    const [comparison, setComparison] = useState('current');
    const [diff, setDiff] = useState(null);
    const [pendingRestore, setPendingRestore] = useState(null);

    useEffect(() => {
        if (!isOpen || !storyId) return;
        let active = true;
        setLoading(true);
        setError('');
        setDiff(null);
        setSelected('');
        setPendingRestore(null);
        getVersions(storyId).then(v => {
            if (active) setVersions(v);
        }).catch(err => { if (active) setError(err.message); })
            .finally(() => { if (active) setLoading(false); });
        return () => { active = false; };
    }, [isOpen, storyId, getVersions]);

    useEffect(() => {
        if (!isOpen || !selected) return;
        const controller = new AbortController();
        setDiff(null);
        const compare = async () => {
            try {
                const before = await getVersion(storyId, selected);
                const after = comparison === 'current' ? currentStory : await getVersion(storyId, comparison);
                if (!before || before.error || !after || after.error) throw new Error(t('versions.compareLoadError'));
                const result = await compareStories(before, after, { signal: controller.signal });
                if (!controller.signal.aborted) setDiff(result);
            } catch (err) {
                if (!controller.signal.aborted) setError(err.message);
            }
        };
        compare();
        return () => controller.abort();
    }, [isOpen, storyId, selected, comparison, currentStory, t]);

    const handleRestore = async (version) => {
        setRestoring(true);
        setError('');
        try {
            await onRestore(version.uuid || version.version);
            onClose();
        } catch (err) {
            setError(err.message);
        } finally {
            setRestoring(false);
        }
    };

    if (!isOpen) return null;
    return <div className="quality-overlay">
        <section className="quality-dialog" role="dialog" aria-modal="true" aria-labelledby="versions-title">
            <header><div><h2 id="versions-title">{t('versions.title')}</h2><p>{t('versions.subtitle')}</p></div>
                <button onClick={onClose} disabled={restoring}>{t('generic.close')}</button></header>
            <div className="quality-content">
                {error && <p role="alert">{error}</p>}
                {pendingRestore && <div className="quality-finding" role="alert">
                    <p>{t('versions.restoreConfirm', { version: pendingRestore.version })}</p>
                    <button onClick={() => setPendingRestore(null)} disabled={restoring}>{t('versions.cancelRestore')}</button>{' '}
                    <button onClick={() => handleRestore(pendingRestore)} disabled={restoring}>{t(restoring ? 'versions.restoring' : 'versions.restoreSnapshot')}</button>
                </div>}
                {loading ? <p>{t('versions.loading')}</p> : versions.length === 0 ? <p>{t('versions.empty')}</p> : <>
                    <label>{t('versions.compareWith')} <select value={comparison} onChange={e => setComparison(e.target.value)}>
                        <option value="current">{t('versions.currentStory')}</option>
                        {versions.map(v => <option key={v.uuid} value={v.uuid}>{t('versions.versionSummary', { version: v.version, summary: v.summary })}</option>)}
                    </select></label>
                    {[...versions].reverse().map(v => <article className="quality-finding" key={v.uuid}>
                        <strong>{t('versions.versionSummary', { version: v.version, summary: v.summary })}</strong>
                        <p>{new Date(v.timestamp * 1000).toLocaleString()}</p>
                        <small>{t('versions.snapshot', { uuid: v.uuid })}</small>
                        <button aria-pressed={selected === v.uuid} onClick={() => setSelected(v.uuid)}>{t('versions.reviewChanges')}</button>{' '}
                        <button onClick={() => setPendingRestore(v)} disabled={restoring}>{t('versions.restore')}</button>
                        {selected === v.uuid && (diff ? <StoryChanges diff={diff} /> : <p>{t('versions.comparing')}</p>)}
                    </article>)}
                </>}
            </div>
        </section>
    </div>;
};

export default VersionHistoryDialog;
