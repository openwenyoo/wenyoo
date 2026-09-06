import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { getVersion } from '../services/storyService';
import StoryChanges from './StoryChanges';
import './story-quality.css';

const VersionHistoryDialog = ({ isOpen, onClose, storyId, getVersions, onRestore, currentStory }) => {
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
                if (!before || before.error || !after || after.error) throw new Error('Could not load versions for comparison.');
                const result = await axios.post('/api/story-quality/diff', { before, after }, { signal: controller.signal });
                if (!controller.signal.aborted) setDiff(result.data);
            } catch (err) {
                if (!controller.signal.aborted) setError(err.message);
            }
        };
        compare();
        return () => controller.abort();
    }, [isOpen, storyId, selected, comparison, currentStory]);

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
            <header><div><h2 id="versions-title">Story version history</h2><p>Inspect a snapshot, compare changes, or restore your work.</p></div>
                <button onClick={onClose} disabled={restoring}>Close</button></header>
            <div className="quality-content">
                {error && <p role="alert">{error}</p>}
                {pendingRestore && <div className="quality-finding" role="alert">
                    <p>Restore version {pendingRestore.version}? Your current story, including unsaved edits, will be backed up first.</p>
                    <button onClick={() => setPendingRestore(null)} disabled={restoring}>Cancel restore</button>{' '}
                    <button onClick={() => handleRestore(pendingRestore)} disabled={restoring}>{restoring ? 'Restoring…' : 'Restore snapshot'}</button>
                </div>}
                {loading ? <p>Loading versions…</p> : versions.length === 0 ? <p>Save your story to create its first snapshot.</p> : <>
                    <label>Compare selected snapshot with <select value={comparison} onChange={e => setComparison(e.target.value)}>
                        <option value="current">Current editor story</option>
                        {versions.map(v => <option key={v.uuid} value={v.uuid}>Version {v.version} · {v.summary}</option>)}
                    </select></label>
                    {[...versions].reverse().map(v => <article className="quality-finding" key={v.uuid}>
                        <strong>Version {v.version} · {v.summary}</strong>
                        <p>{new Date(v.timestamp * 1000).toLocaleString()}</p>
                        <small>Snapshot {v.uuid}</small>
                        <button aria-pressed={selected === v.uuid} onClick={() => setSelected(v.uuid)}>Review changes</button>{' '}
                        <button onClick={() => setPendingRestore(v)} disabled={restoring}>Restore</button>
                        {selected === v.uuid && (diff ? <StoryChanges diff={diff} /> : <p>Comparing…</p>)}
                    </article>)}
                </>}
            </div>
        </section>
    </div>;
};

export default VersionHistoryDialog;
