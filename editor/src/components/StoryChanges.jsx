import React from 'react';

export default function StoryChanges({ diff }) {
    if (!diff) return null;
    return <div className="story-changes">
        <p>{diff.counts.added} added · {diff.counts.removed} removed · {diff.counts.modified} modified</p>
        {diff.changes.length === 0 && <p>No story changes.</p>}
        {diff.changes.map((change, i) => <details key={i}>
            <summary><strong>{change.kind}</strong> {change.path.join(' → ') || 'Story'}</summary>
            <div className="change-columns">
                <div><h4>Before</h4><pre>{JSON.stringify(change.before, null, 2)}</pre></div>
                <div><h4>After</h4><pre>{JSON.stringify(change.after, null, 2)}</pre></div>
            </div>
        </details>)}
    </div>;
}
