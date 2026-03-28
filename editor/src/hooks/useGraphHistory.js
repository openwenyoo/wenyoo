import { useState, useCallback, useEffect, useRef, useMemo } from 'react';

/**
 * Custom hook for managing graph history (undo/redo)
 * @param {number} maxHistorySize - Maximum number of history states to keep
 * @returns {Object} History state and control functions
 */
export const useGraphHistory = (maxHistorySize = 50) => {
    const [history, setHistory] = useState([]);
    const [historyIndex, setHistoryIndex] = useState(-1);
    const [savedHistoryIndex, setSavedHistoryIndex] = useState(-1);

    // Initial state hash to detect "true" changes (Create + Delete = Clean)
    const [savedStateHash, setSavedStateHash] = useState(null);

    const generateHash = (nodes, edges) => {
        // Helper to remove transient ReactFlow fields that shouldn't affect "unsaved" status
        const sanitizeNode = (node) => {
            // Destructure to exclude specific fields
            const {
                selected, dragging, positionAbsolute, measured,
                width, height, resizing, handleBounds,
                ...rest
            } = node;
            return rest;
        };

        const sanitizeEdge = (edge) => {
            const { selected, ...rest } = edge;
            return rest;
        };

        // Create clean copies
        const cleanNodes = nodes.map(sanitizeNode);
        const cleanEdges = edges.map(sanitizeEdge);

        return JSON.stringify({ nodes: cleanNodes, edges: cleanEdges });
    };

    // Helper to save state to history
    const addToHistory = useCallback((newNodes, newEdges) => {
        const currentState = { nodes: newNodes, edges: newEdges };
        const newHash = generateHash(newNodes, newEdges);

        console.log("[HistoryDebug] Attempting to add. NewHash:", newHash.substring(0, 20) + "...");

        // Don't add if identical to current top of history (deduplicate)
        if (historyIndex >= 0 && generateHash(history[historyIndex].nodes, history[historyIndex].edges) === newHash) {
            console.log("[HistoryDebug] Duplicate state ignored.");
            return;
        }

        const newHistory = history.slice(0, historyIndex + 1);
        newHistory.push(currentState);

        // Limit history size
        if (newHistory.length > maxHistorySize) {
            newHistory.shift();
            // We lose the "saved index" reference if it slides off, but hash remains valid
            // If the saved index was 0 and we shift, it becomes -1 (invalid).
            // But if we use Hash for dirty checking, we don't care about index shifting as much!
            setSavedHistoryIndex(prev => Math.max(-1, prev - 1));
        }

        setHistory(newHistory);
        setHistoryIndex(newHistory.length - 1);
    }, [history, historyIndex, maxHistorySize]);

    const handleUndo = useCallback(() => {
        if (historyIndex > 0) {
            return history[historyIndex - 1];
        }
        return null;
    }, [history, historyIndex]);

    const handleRedo = useCallback(() => {
        if (historyIndex < history.length - 1) {
            return history[historyIndex + 1];
        }
        return null;
    }, [history, historyIndex]);

    // Mark current state as saved
    const markAsSaved = useCallback(() => {
        if (historyIndex >= 0 && history[historyIndex]) {
            console.log("[HistoryDebug] Marking as saved. Index:", historyIndex);
            setSavedHistoryIndex(historyIndex);
            const hash = generateHash(history[historyIndex].nodes, history[historyIndex].edges);
            setSavedStateHash(hash);
            console.log("[HistoryDebug] Saved Hash:", hash.substring(0, 20) + "...");
        }
    }, [history, historyIndex]);

    // Reset history with initial clean state
    const clearHistory = useCallback((initialNodes, initialEdges) => {
        console.log("[HistoryDebug] Clearing history.");
        const initialState = { nodes: initialNodes, edges: initialEdges };
        const hash = generateHash(initialNodes, initialEdges);
        setHistory([initialState]);
        setHistoryIndex(0);
        setSavedHistoryIndex(0);
        setSavedStateHash(hash);
        console.log("[HistoryDebug] Initial Hash:", hash.substring(0, 20) + "...");
    }, []);

    const canUndo = historyIndex > 0;
    const canRedo = historyIndex < history.length - 1;

    // Calculate dirty state based on HASH, not index
    // This solves "Create + Delete = Dirty" -> Now it will be Clean
    const isDirty = useMemo(() => {
        if (historyIndex < 0 || !history[historyIndex]) return false;
        const currentHash = generateHash(history[historyIndex].nodes, history[historyIndex].edges);

        console.log(`[HistoryDebug] check dirty. Current: ${currentHash.substring(0, 20)}... Saved: ${savedStateHash ? savedStateHash.substring(0, 20) : 'null'}... Match: ${currentHash === savedStateHash}`);

        return currentHash !== savedStateHash;
    }, [history, historyIndex, savedStateHash]);

    // Count is just 1 if dirty, 0 if clean (simplifying from "number of steps")
    // Or we can keep number of steps for UI feedback, but strict 0 when clean.
    // If hashes match, unsavedCount MUST be 0.
    // If hashes differ, we can fall back to index diff for a magnitude estimate.
    const unsavedCount = isDirty ? Math.abs(historyIndex - savedHistoryIndex) || 1 : 0;

    // Get ref for addToHistory to avoid dependency cycles
    const addToHistoryRef = useRef(addToHistory);
    useEffect(() => {
        addToHistoryRef.current = addToHistory;
    }, [addToHistory]);

    return {
        history,
        historyIndex,
        setHistoryIndex,
        addToHistory,
        addToHistoryRef,
        handleUndo,
        handleRedo,
        canUndo,
        canRedo,
        markAsSaved,
        unsavedCount,
        clearHistory
    };
};
