import React from 'react';
import { useLocale } from '../i18n';

export default function StoryChanges({ diff }) {
    const { t } = useLocale();
    if (!diff) return null;
    return <div className="story-changes">
        <p>{t('quality.changeCounts', diff.counts)}</p>
        {diff.changes.length === 0 && <p>{t('quality.noChanges')}</p>}
        {diff.changes.map((change, i) => <details key={i}>
            <summary><strong>{t(`quality.change.${change.kind}`)}</strong> {change.path.join(' → ') || t('quality.story')}</summary>
            <div className="change-columns">
                <div><h4>{t('quality.before')}</h4><pre>{JSON.stringify(change.before, null, 2)}</pre></div>
                <div><h4>{t('quality.after')}</h4><pre>{JSON.stringify(change.after, null, 2)}</pre></div>
            </div>
        </details>)}
    </div>;
}
