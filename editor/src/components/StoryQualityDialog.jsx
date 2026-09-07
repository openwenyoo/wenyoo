import React, { useEffect, useState } from 'react';
import StoryChanges from './StoryChanges';
import { useLocale } from '../i18n';
import { compareStories, playtestStory, validateStory } from '../services/storyService';
import '../styles/story-quality.css';

export default function StoryQualityDialog({ snapshot, onClose, onReveal }) {
    const { t } = useLocale();
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
                    validateStory(snapshot.story, { signal: controller.signal }),
                    compareStories(snapshot.before, snapshot.story, { signal: controller.signal }),
                ]);
                setIssues(validation.issues);
                setDiff(comparison);
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
            const response = await playtestStory(
                snapshot.story,
                steps,
                commands.split('\n').map(c => c.trim()).filter(Boolean),
            );
            setReport(response);
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
        <strong>{t(issue.severity === 'error' ? 'generic.error' : 'quality.review')} · {issue.code.replaceAll('_', ' ')}</strong>
        <p>{issue.message}</p>
        {issue.hint && <p className="quality-hint">{issue.hint}</p>}
        {issue.path?.length > 0 && <small>{issue.path.join(' → ')}</small>}
        {issue.entity_id && canReveal(issue) && <button onClick={() => onReveal(issue)}>{t('quality.openEntity', { id: issue.entity_id })}</button>}
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
            <header><div><h2 id="quality-title">{t('quality.title')}</h2><p>{t('quality.subtitle')}</p></div>
                <button onClick={onClose} disabled={busy} aria-label={t('quality.closeLabel')}>{t('generic.close')}</button></header>
            <nav aria-label={t('quality.toolsLabel')}>
                {['validate', 'playtest', 'changes'].map(id =>
                    <button key={id} aria-pressed={tab === id} onClick={() => setTab(id)}>{t(`quality.tab.${id}`)}</button>)}
            </nav>
            {error && <p role="alert" className="quality-error">{typeof error === 'string' ? error : JSON.stringify(error)}</p>}
            <div className="quality-content">
                {tab === 'validate' && <>
                    {issues === null ? <p>{t('quality.checking')}</p> : <>
                        <p>{t('quality.issueCounts', {
                            errors: issues.filter(i => i.severity === 'error').length,
                            warnings: issues.filter(i => i.severity === 'warning').length,
                        })}</p>
                        {issues.length === 0 && <p>{t('quality.noProblems')}</p>}
                        {findings(issues)}
                    </>}
                </>}
                {tab === 'changes' && <><p>{t(snapshot.tab === 'changes' ? 'quality.aiChanges' : 'quality.savedChanges')}</p><StoryChanges diff={diff} /></>}
                {tab === 'playtest' && <>
                    <p>{t('quality.playtestHelp')}</p>
                    <label>{t('quality.turnBudget')} <input aria-label={t('quality.turnBudget')} type="number" min="1" max="30" value={steps} onChange={e => setSteps(e.target.value)} disabled={busy} /></label>
                    <label>{t('quality.sampleCommands')}<textarea rows="3" value={commands} onChange={e => setCommands(e.target.value)} disabled={busy} placeholder={t('quality.commandPlaceholder')} /></label>
                    <button onClick={run} disabled={busy || !issues || issues.some(i => i.severity === 'error') || !Number.isInteger(Number(steps)) || Number(steps) < 1 || Number(steps) > 30}>
                        {t(busy ? 'quality.exploring' : 'quality.run')}
                    </button>
                    {issues?.some(i => i.severity === 'error') && <p>{t('quality.fixErrors')}</p>}
                    {report && <>
                        <p><strong>{report.status}</strong> · {t('quality.reportStats', {
                            turns: report.steps.length,
                            nodes: report.visited_nodes.length,
                            endings: report.ending_nodes.length,
                        })}</p>
                        <p>{t(report.limited ? 'quality.budgetReached' : 'quality.explorationFinished')} {t('quality.sampleDisclaimer')}</p>
                        <p>{t('quality.unvisited', { nodes: report.unvisited_nodes.join(', ') || t('quality.none') })}</p>
                        <button onClick={download}>{t('quality.download')}</button>
                        {findings(report.findings)}
                        {report.steps.map((step, i) => <details key={i}><summary>{i + 1}. {step.command} · {step.from} → {step.to || '?'}</summary><p>{step.error || step.narrative}</p><small>{step.path.join(' → ')}</small></details>)}
                    </>}
                </>}
            </div>
        </section>
    </div>;
}
