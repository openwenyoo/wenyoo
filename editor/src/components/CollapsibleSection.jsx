import React, { useState } from 'react';

export const CollapsibleSection = ({ title, children, defaultOpen = false, isDimmed = false }) => {
    const [isOpen, setIsOpen] = useState(defaultOpen);

    return (
        <div className={`collapsible-section ${isDimmed ? 'dimmed' : ''}`}>
            <div className="section-header" onClick={() => setIsOpen(!isOpen)}>
                <h4>{title}</h4>
                <span>{isOpen ? '▼' : '►'}</span>
            </div>
            {isOpen && <div className="section-content">{children}</div>}
        </div>
    );
};