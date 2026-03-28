/**
 * Story Analyzer - Analyzes story content to extract metadata, style, and themes
 * Results are cached in the story YAML metadata section
 */

/**
 * Main analysis function - analyzes entire story
 * @param {Object} storyData - The story data with nodes
 * @returns {Object} Analysis results to be cached
 */
export function analyzeStory(storyData) {
    const nodes = Array.isArray(storyData.nodes)
        ? storyData.nodes
        : Object.values(storyData.nodes || {});

    if (!nodes || nodes.length === 0) {
        return {
            vibe: 'unknown',
            tone: 'unknown',
            vocabulary_level: 'unknown',
            perspective: 'unknown',
            themes: [],
            last_analyzed: new Date().toISOString()
        };
    }

    return {
        vibe: detectVibe(nodes),
        tone: analyzeTone(nodes),
        vocabulary_level: analyzeVocabulary(nodes),
        perspective: detectPerspective(nodes),
        themes: extractThemes(nodes),
        last_analyzed: new Date().toISOString()
    };
}

/**
 * Detect the overall vibe/atmosphere of the story
 * @param {Array} nodes - Story nodes
 * @returns {string} Detected vibe
 */
function detectVibe(nodes) {
    const vibeKeywords = {
        horror: ['dark', 'shadow', 'fear', 'terror', 'blood', 'death', 'ghost', 'haunted', 'scream', 'nightmare'],
        mystery: ['clue', 'investigate', 'suspect', 'detective', 'mystery', 'secret', 'hidden', 'puzzle', 'enigma'],
        fantasy: ['magic', 'spell', 'dragon', 'wizard', 'enchanted', 'mystical', 'realm', 'quest', 'legendary'],
        scifi: ['robot', 'space', 'alien', 'technology', 'future', 'cyber', 'android', 'quantum', 'starship'],
        adventure: ['explore', 'journey', 'treasure', 'adventure', 'discover', 'expedition', 'quest', 'voyage'],
        comedy: ['funny', 'laugh', 'joke', 'silly', 'ridiculous', 'absurd', 'hilarious', 'amusing'],
        romance: ['love', 'heart', 'romance', 'passion', 'kiss', 'beloved', 'affection', 'desire'],
        thriller: ['suspense', 'chase', 'danger', 'escape', 'tense', 'urgent', 'threat', 'pursuit']
    };

    const allText = nodes
        .map(n => `${n.description || ''} ${n.name || ''}`)
        .join(' ')
        .toLowerCase();

    const scores = {};
    for (const [vibe, keywords] of Object.entries(vibeKeywords)) {
        scores[vibe] = keywords.filter(kw => allText.includes(kw)).length;
    }

    // Get top 2 vibes
    const sortedVibes = Object.entries(scores)
        .sort(([, a], [, b]) => b - a)
        .filter(([, score]) => score > 0)
        .slice(0, 2)
        .map(([vibe]) => vibe);

    return sortedVibes.length > 0 ? sortedVibes.join(', ') : 'general fiction';
}

/**
 * Analyze the tone of the writing
 * @param {Array} nodes - Story nodes
 * @returns {string} Detected tone
 */
function analyzeTone(nodes) {
    const toneIndicators = {
        dark: ['shadow', 'grim', 'ominous', 'foreboding', 'sinister', 'bleak'],
        light: ['bright', 'cheerful', 'pleasant', 'warm', 'joyful', 'happy'],
        serious: ['grave', 'solemn', 'important', 'critical', 'significant'],
        playful: ['playful', 'whimsical', 'mischievous', 'lighthearted'],
        mysterious: ['mysterious', 'enigmatic', 'cryptic', 'obscure', 'strange'],
        dramatic: ['dramatic', 'intense', 'powerful', 'striking', 'vivid']
    };

    const sampleText = nodes
        .slice(0, 5)
        .map(n => n.description || '')
        .join(' ')
        .toLowerCase();

    const toneScores = {};
    for (const [tone, indicators] of Object.entries(toneIndicators)) {
        toneScores[tone] = indicators.filter(ind => sampleText.includes(ind)).length;
    }

    const detectedTones = Object.entries(toneScores)
        .sort(([, a], [, b]) => b - a)
        .filter(([, score]) => score > 0)
        .slice(0, 2)
        .map(([tone]) => tone);

    return detectedTones.length > 0 ? detectedTones.join(', ') : 'neutral';
}

/**
 * Analyze vocabulary complexity
 * @param {Array} nodes - Story nodes
 * @returns {string} Vocabulary level
 */
function analyzeVocabulary(nodes) {
    const sampleText = nodes
        .slice(0, 3)
        .map(n => n.description || '')
        .join(' ');

    const words = sampleText.split(/\s+/).filter(w => w.length > 0);
    if (words.length === 0) return 'basic';

    const avgWordLength = words.reduce((sum, w) => sum + w.length, 0) / words.length;

    // Simple heuristic based on average word length
    if (avgWordLength < 4.5) return 'basic';
    if (avgWordLength < 5.5) return 'intermediate';
    return 'advanced';
}

/**
 * Detect narrative perspective
 * @param {Array} nodes - Story nodes
 * @returns {string} Narrative perspective
 */
function detectPerspective(nodes) {
    const sampleText = nodes
        .slice(0, 3)
        .map(n => n.description || '')
        .join(' ')
        .toLowerCase();

    const firstPersonCount = (sampleText.match(/\b(i|me|my|mine|we|us|our)\b/g) || []).length;
    const secondPersonCount = (sampleText.match(/\b(you|your|yours)\b/g) || []).length;
    const thirdPersonCount = (sampleText.match(/\b(he|she|him|her|his|hers|they|them|their)\b/g) || []).length;

    const max = Math.max(firstPersonCount, secondPersonCount, thirdPersonCount);

    if (max === 0) return 'unknown';
    if (secondPersonCount === max) return 'second person';
    if (firstPersonCount === max) return 'first person';
    return 'third person';
}

/**
 * Extract recurring themes from the story
 * @param {Array} nodes - Story nodes
 * @returns {Array<string>} Detected themes
 */
function extractThemes(nodes) {
    const themeKeywords = {
        isolation: ['alone', 'isolated', 'solitary', 'lonely', 'abandoned'],
        supernatural: ['ghost', 'spirit', 'supernatural', 'paranormal', 'otherworldly', 'spectral'],
        investigation: ['investigate', 'clue', 'search', 'examine', 'discover', 'uncover'],
        survival: ['survive', 'escape', 'danger', 'threat', 'peril', 'deadly'],
        betrayal: ['betray', 'deceive', 'lie', 'trick', 'backstab', 'treachery'],
        redemption: ['redeem', 'atone', 'forgive', 'salvation', 'second chance'],
        power: ['power', 'control', 'dominate', 'rule', 'authority', 'command'],
        freedom: ['freedom', 'liberty', 'escape', 'break free', 'independence']
    };

    const allText = nodes
        .map(n => `${n.description || ''} ${n.name || ''}`)
        .join(' ')
        .toLowerCase();

    const detectedThemes = [];
    for (const [theme, keywords] of Object.entries(themeKeywords)) {
        const matches = keywords.filter(kw => allText.includes(kw)).length;
        if (matches >= 2) {
            detectedThemes.push(theme);
        }
    }

    return detectedThemes.slice(0, 5); // Return top 5 themes
}

/**
 * Generate a brief outline of the story structure
 * @param {Array} nodes - Story nodes
 * @returns {string} Brief outline
 */
export function generateOutline(nodes) {
    if (!nodes || nodes.length === 0) return 'No nodes in story';

    const maxNodes = 10;
    const nodesToShow = nodes.slice(0, maxNodes);

    const outline = nodesToShow.map(node => {
        const desc = node.description || 'No description';
        const summary = desc.length > 60 ? desc.substring(0, 60) + '...' : desc;

        // Count connections
        const actionCount = node.actions?.length || 0;
        const objectCount = node.objects?.length || 0;

        return `- ${node.id}: ${summary} (${actionCount} actions, ${objectCount} objects)`;
    }).join('\n');

    const remaining = nodes.length - maxNodes;
    const suffix = remaining > 0 ? `\n... and ${remaining} more nodes` : '';

    return outline + suffix;
}
