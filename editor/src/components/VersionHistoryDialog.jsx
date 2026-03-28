import React, { useState, useEffect } from 'react';

const VersionHistoryDialog = ({ isOpen, onClose, storyId, getVersions, onRestore }) => {
    const [versions, setVersions] = useState([]);
    const [loading, setLoading] = useState(true);
    const [restoring, setRestoring] = useState(false);

    useEffect(() => {
        if (isOpen && storyId) {
            setLoading(true);
            getVersions(storyId).then(v => {
                setVersions(v);
                setLoading(false);
            });
        }
    }, [isOpen, storyId, getVersions]);

    const handleRestore = async (version) => {
        if (confirm(`Restore to version ${version}? Your current changes will be backed up as a new version.`)) {
            setRestoring(true);
            await onRestore(version);
            setRestoring(false);
            onClose();
        }
    };

    const formatDate = (timestamp) => {
        const date = new Date(timestamp * 1000);
        return date.toLocaleString();
    };

    const getVersionLabel = (version, index, total) => {
        if (version === 0) return 'Original (when first opened)';
        if (index === total - 1) return `Version ${version} (latest backup)`;
        return `Version ${version}`;
    };

    if (!isOpen) return null;

    return (
        <div className="version-history-overlay" onClick={onClose}>
            <div className="version-history-dialog" onClick={e => e.stopPropagation()}>
                <div className="version-history-header">
                    <h3>Version History</h3>
                    <button className="close-btn" onClick={onClose}>×</button>
                </div>
                <div className="version-history-content">
                    {loading ? (
                        <div className="version-loading">Loading versions...</div>
                    ) : versions.length === 0 ? (
                        <div className="version-empty">No versions available yet. Save your story to create backups.</div>
                    ) : (
                        <div className="version-list">
                            {versions.map((v, index) => (
                                <div key={v.version} className="version-item">
                                    <div className="version-info">
                                        <span className="version-label">
                                            {getVersionLabel(v.version, index, versions.length)}
                                        </span>
                                        <span className="version-date">{formatDate(v.timestamp)}</span>
                                    </div>
                                    <button
                                        className="restore-btn"
                                        onClick={() => handleRestore(v.version)}
                                        disabled={restoring}
                                    >
                                        Restore
                                    </button>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
                <div className="version-history-footer">
                    <p className="version-note">
                        Restoring a version will backup your current story first.
                    </p>
                </div>
            </div>
        </div>
    );
};

export default VersionHistoryDialog;
