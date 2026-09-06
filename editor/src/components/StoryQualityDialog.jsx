import React, { useEffect, useState } from 'react';
import axios from 'axios';
import StoryChanges from './StoryChanges';
import './story-quality.css';

export default function StoryQualityDialog({ snapshot, onClose, onReveal }) {
    const [tab, setTab] = useState(snapshot.tab || 'validate');
    const [issues, setIssues] = useState(null);
    const [diff, setDiff] = useState(null);
    const [report, setReport] = useState(null);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');
    const [steps, setSteps] = useState(8);
    const [commands, setCommands] = useState('');

    useEffect(() => {
        const controller = new AbortController();
        const check = async () => {
            try {
                const [validation, comparison] = await Promise.all([
                    axios.post('/api/story-quality/validate', { story: snapshot.story }, { signal: controller.signal }),
                    axios.post('/api/story-quality/diff', { before: snapshot.before, after: snapshot.story }, { signal: controller.signal }),
                ]);
                setIssues(validation.data.issues);
                setDiff(comparison.data);
            } catch (err) {
                if (!controller.signal.aborted) setError(err.response?.data?.detail || err.message);
            }
        };
        check();
        return () => controller.abort();
    }, [snapshot]);

    const run = async () => {
        setBusy(true);
        setError('');
        try {
            const response = await axios.post('/api/story-quality/playtest', {
                story: snapshot.story, max_steps: Number(steps), max_depth: 4,
                commands: commands.split('\n').map(c => c.trim()).filter(Boolean),
            });
            setReport(response.data);
        } catch (err) {
            setError(err.response?.data?.detail || err.message);
        } finally {
            setBusy(false);
        }
    };
    const canReveal = (issue) => {
        if (issue.entity_type === 'node') return Boolean(snapshot.story.nodes?.[issue.entity_id]);
        if (issue.entity_type === 'character') return snapshot.story.characters?.some(c => c.id === issue.entity_id);
        if (issue.entity_type === 'connection') return snapshot.story.connections?.some(c => c.id === issue.entity_id);
        if (issue.entity_type === 'object') return snapshot.story.objects?.some(o => o.id === issue.entity_id)
            || Object.values(snapshot.story.nodes || {}).some(n => n?.objects?.some(o => o.id === issue.entity_id));
        return false;
    };
    const findings = (items) => items.map((issue, i) => <article className={`quality-finding ${issue.severity}`} key={i}>
        <strong>{issue.severity === 'error' ? 'Error' : 'Review'} · {issue.code.replaceAll('_', ' ')}</strong>
        <p>{issue.message}</p>
        {issue.hint && <p className="quality-hint">{issue.hint}</p>}
        {issue.path?.length > 0 && <small>{issue.path.join(' → ')}</small>}
        {issue.entity_id && canReveal(issue) && <button onClick={() => onReveal(issue)}>Open {issue.entity_id}</button>}
    </article>);
    const download = () => {
        const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' }));
        const link = document.createElement('a');
        link.href = url;
        link.download = `${snapshot.story.id || 'story'}-playtest.json`;
        link.click();
        URL.revokeObjectURL(url);
    };

    return <div className="quality-overlay">
        <section className="quality-dialog" role="dialog" aria-modal="true" aria-labelledby="quality-title">
            <header><div><h2 id="quality-title">Story quality</h2><p>Review your current unsaved story.</p></div>
                <button onClick={onClose} disabled={busy} aria-label="Close story quality">Close</button></header>
            <nav aria-label="Story quality tools">
                {[['validate', 'Validation'], ['playtest', 'Auto-test'], ['changes', 'Changes']].map(([id, label]) =>
                    <button key={id} aria-pressed={tab === id} onClick={() => setTab(id)}>{label}</button>)}
            </nav>
            {error && <p role="alert" className="quality-error">{typeof error === 'string' ? error : JSON.stringify(error)}</p>}
            <div className="quality-content">
                {tab === 'validate' && <>
                    {issues === null ? <p>Checking story…</p> : <>
                        <p>{issues.filter(i => i.severity === 'error').length} errors · {issues.filter(i => i.severity === 'warning').length} items to review</p>
                        {issues.length === 0 && <p>No structural problems found. Run a playtest to check behavior.</p>}
                        {findings(issues)}
                    </>}
                </>}
                {tab === 'changes' && <><p>{snapshot.tab === 'changes' ? 'Changes made during the last AI edit.' : 'Changes since the story was loaded or saved.'}</p><StoryChanges diff={diff} /></>}
                {tab === 'playtest' && <>
                    <p>Explore available actions using your configured model. Runs in temporary sessions and consumes model tokens. Forms and ambiguous choices are reported for manual testing.</p>
                    <label>Player-turn budget <input aria-label="Player-turn budget" type="number" min="1" max="30" value={steps} onChange={e => setSteps(e.target.value)} disabled={busy} /></label>
                    <label>Optional sample commands, one per line (up to 10)<textarea rows="3" value={commands} onChange={e => setCommands(e.target.value)} disabled={busy} placeholder="Look for a hidden exit" /></label>
                    <button onClick={run} disabled={busy || !issues || issues.some(i => i.severity === 'error') || !Number.isInteger(Number(steps)) || Number(steps) < 1 || Number(steps) > 30}>
                        {busy ? 'Exploring story…' : 'Run auto-test'}
                    </button>
                    {issues?.some(i => i.severity === 'error') && <p>Fix validation errors before running.</p>}
                    {report && <>
                        <p><strong>{report.status}</strong> · {report.steps.length} turns · {report.visited_nodes.length} nodes visited · {report.ending_nodes.length} endings reached</p>
                        <p>{report.limited ? 'Budget reached; some paths remain unexplored.' : 'Exploration finished for the available actions.'} This is a sampled test, not proof that every path works.</p>
                        <p>Unvisited: {report.unvisited_nodes.join(', ') || 'none'}</p>
                        <button onClick={download}>Download report</button>
                        {findings(report.findings)}
                        {report.steps.map((step, i) => <details key={i}><summary>{i + 1}. {step.command} · {step.from} → {step.to || '?'}</summary><p>{step.error || step.narrative}</p><small>{step.path.join(' → ')}</small></details>)}
                    </>}
                </>}
            </div>
        </section>
    </div>;
}
