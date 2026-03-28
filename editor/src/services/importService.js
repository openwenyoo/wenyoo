import { CharacterCard } from '@lenml/char-card-reader';

export const IMPORT_SOURCE_TYPES = {
    CHARACTER_CARD: 'character_card',
    MARKDOWN: 'markdown',
    TEXT: 'text',
    PDF: 'pdf',
};

export const SUPPORTED_IMPORT_ACCEPT = '.png,.jpg,.jpeg,.webp,.json,.md,.markdown,.txt';

const MARKDOWN_EXTENSIONS = new Set(['md', 'markdown']);
const TEXT_EXTENSIONS = new Set(['txt']);
const CARD_IMAGE_EXTENSIONS = new Set(['png', 'jpg', 'jpeg', 'webp']);

const getFileExtension = (filename = '') => {
    const parts = filename.toLowerCase().split('.');
    return parts.length > 1 ? parts.pop() : '';
};

const filenameWithoutExtension = (filename = 'imported_source') => {
    const lastDot = filename.lastIndexOf('.');
    return lastDot > 0 ? filename.slice(0, lastDot) : filename;
};

const normalizeId = (value = 'item') => (
    value
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '_')
        .replace(/^_+|_+$/g, '')
        || 'item'
);

const normalizeText = (value) => (typeof value === 'string' ? value.trim() : '');

const compactText = (...parts) => (
    parts
        .flat()
        .map(normalizeText)
        .filter(Boolean)
        .join('\n\n')
);

const summarizeText = (text, maxLength = 300) => {
    const normalized = normalizeText(text).replace(/\s+/g, ' ');
    if (!normalized) return '';
    if (normalized.length <= maxLength) return normalized;
    return `${normalized.slice(0, maxLength - 3).trim()}...`;
};

const parseMarkdownSections = (text) => {
    const sectionRegex = /^(#{1,6})\s+(.+)$/gm;
    const matches = [...text.matchAll(sectionRegex)];
    const sections = [];

    matches.forEach((match, index) => {
        const startIndex = match.index ?? 0;
        const endIndex = index + 1 < matches.length ? (matches[index + 1].index ?? text.length) : text.length;
        const body = text.slice(startIndex + match[0].length, endIndex).trim();
        sections.push({
            heading: match[2].trim(),
            level: match[1].length,
            content: body,
        });
    });

    return sections;
};

const extractMarkdownTitle = (filename, sections, text) => {
    const firstHeading = sections.find(section => section.level === 1) || sections[0];
    if (firstHeading?.heading) return firstHeading.heading;

    const firstNonEmptyLine = text.split('\n').map(line => line.trim()).find(Boolean);
    if (firstNonEmptyLine) return firstNonEmptyLine.slice(0, 80);

    return filenameWithoutExtension(filename);
};

const deriveMarkdownScenario = (sections) => {
    const likelySection = sections.find(section =>
        /scenario|premise|plot|story|setting/i.test(section.heading)
    );
    return likelySection?.content || '';
};

const deriveWorldInfoFromSections = (sections) => (
    sections
        .filter(section => /world|lore|setting|location|background/i.test(section.heading))
        .slice(0, 8)
        .map(section => ({
            title: section.heading,
            content: section.content,
        }))
);

const deriveCharactersFromSections = (sections) => (
    sections
        .filter(section => /character|cast|npc|people/i.test(section.heading))
        .slice(0, 6)
        .map((section, index) => ({
            id: normalizeId(section.heading || `character_${index + 1}`),
            name: section.heading,
            description: summarizeText(section.content, 240),
            sourceSection: section.heading,
        }))
);

const inferSourceType = (file) => {
    const extension = getFileExtension(file?.name);
    const mimeType = (file?.type || '').toLowerCase();

    if (CARD_IMAGE_EXTENSIONS.has(extension) || mimeType.startsWith('image/')) {
        return IMPORT_SOURCE_TYPES.CHARACTER_CARD;
    }

    if (extension === 'json' || mimeType === 'application/json') {
        return IMPORT_SOURCE_TYPES.CHARACTER_CARD;
    }

    if (MARKDOWN_EXTENSIONS.has(extension) || mimeType.includes('markdown')) {
        return IMPORT_SOURCE_TYPES.MARKDOWN;
    }

    if (TEXT_EXTENSIONS.has(extension) || mimeType.startsWith('text/')) {
        return IMPORT_SOURCE_TYPES.TEXT;
    }

    if (extension === 'pdf' || mimeType === 'application/pdf') {
        return IMPORT_SOURCE_TYPES.PDF;
    }

    throw new Error(`Unsupported import file type: ${file?.name || 'unknown file'}`);
};

const getCharacterBook = (rawData = {}) => (
    rawData.character_book
    || rawData.characterBook
    || rawData.data?.character_book
    || rawData.data?.characterBook
    || null
);

const normalizeCharacterBookEntries = (characterBook) => {
    const entries = characterBook?.entries;
    if (!Array.isArray(entries)) return [];

    return entries.map((entry, index) => ({
        id: entry.id ?? index + 1,
        keys: entry.keys || [],
        content: normalizeText(entry.content),
        comment: normalizeText(entry.comment),
        name: normalizeText(entry.name),
        constant: Boolean(entry.constant),
        position: normalizeText(entry.position),
    }));
};

const isCharacterCardJson = (jsonData) => {
    if (!jsonData || typeof jsonData !== 'object') return false;
    if (jsonData.spec === 'chara_card_v2' || jsonData.spec === 'chara_card_v3') return true;

    const data = jsonData.data && typeof jsonData.data === 'object' ? jsonData.data : jsonData;
    return ['name', 'description', 'personality', 'scenario', 'first_mes', 'mes_example'].some(
        key => key in data
    );
};

const buildCharacterCardImportDraft = (file, specData, rawCardData) => {
    const rawData = specData?.data && typeof specData.data === 'object' ? specData.data : specData || {};
    const name = normalizeText(rawData.name) || filenameWithoutExtension(file.name);
    const description = normalizeText(rawData.description);
    const personality = normalizeText(rawData.personality);
    const scenario = normalizeText(rawData.scenario);
    const firstMessage = normalizeText(rawData.first_mes || rawCardData?.first_message);
    const exampleDialogue = normalizeText(rawData.mes_example || rawCardData?.mes_example);
    const alternateGreetings = Array.isArray(rawData.alternate_greetings) ? rawData.alternate_greetings.filter(Boolean) : [];
    const characterBook = getCharacterBook(specData) || getCharacterBook(rawCardData) || {};
    const worldInfo = normalizeCharacterBookEntries(characterBook);

    return {
        sourceType: IMPORT_SOURCE_TYPES.CHARACTER_CARD,
        sourceFormat: getFileExtension(file.name) === 'json' ? 'sillytavern_card_json' : 'sillytavern_card_image',
        title: name,
        summary: summarizeText(compactText(description, personality, scenario), 320),
        rawText: compactText(
            description,
            personality,
            scenario,
            firstMessage,
            exampleDialogue,
            alternateGreetings.join('\n'),
            worldInfo.map(entry => `${entry.name || entry.keys.join(', ')}\n${entry.content}`)
        ),
        characters: [{
            id: normalizeId(name),
            name,
            description,
            personality,
            scenario,
            first_message: firstMessage,
            example_dialogue: exampleDialogue,
            alternate_greetings: alternateGreetings,
        }],
        worldInfo,
        scenario,
        styleHints: {
            firstMessage,
            exampleDialogue,
            alternateGreetings,
            systemPrompt: normalizeText(rawData.system_prompt),
            postHistoryInstructions: normalizeText(rawData.post_history_instructions),
            creatorNotes: normalizeText(rawData.creator_notes),
        },
        metadata: {
            filename: file.name,
            mimeType: file.type || '',
            parser: '@lenml/char-card-reader',
            importedAt: new Date().toISOString(),
            cardSpec: specData?.spec || rawData.spec || 'v1_or_unknown',
            cardSpecVersion: specData?.spec_version || rawData.spec_version || '',
            creator: normalizeText(rawData.creator),
            characterVersion: normalizeText(rawData.character_version),
            tags: Array.isArray(rawData.tags) ? rawData.tags.filter(Boolean) : [],
            extensions: rawData.extensions || {},
        },
        importWarnings: [],
        rawSource: specData || rawCardData || {},
    };
};

const parseCharacterCardImport = async (file) => {
    const extension = getFileExtension(file.name);

    if (extension === 'json') {
        const jsonText = await file.text();
        let jsonData;

        try {
            jsonData = JSON.parse(jsonText);
        } catch (error) {
            throw new Error('Invalid JSON file. Could not parse imported character card.');
        }

        if (!isCharacterCardJson(jsonData)) {
            throw new Error('JSON import is only supported for character card JSON right now.');
        }

        const card = CharacterCard.from_json(jsonData);
        const specData = typeof card.toSpecV3 === 'function'
            ? card.toSpecV3()
            : (typeof card.toSpecV2 === 'function' ? card.toSpecV2() : jsonData);

        return buildCharacterCardImportDraft(file, specData, card);
    }

    const arrayBuffer = await file.arrayBuffer();
    const card = await CharacterCard.from_file(arrayBuffer);
    const specData = typeof card.toSpecV3 === 'function'
        ? card.toSpecV3()
        : (typeof card.toSpecV2 === 'function' ? card.toSpecV2() : {});

    return buildCharacterCardImportDraft(file, specData, card);
};

const parseMarkdownImport = async (file) => {
    const text = await file.text();
    const sections = parseMarkdownSections(text);
    const title = extractMarkdownTitle(file.name, sections, text);
    const worldInfo = deriveWorldInfoFromSections(sections);
    const characters = deriveCharactersFromSections(sections);
    const scenario = deriveMarkdownScenario(sections);

    return {
        sourceType: IMPORT_SOURCE_TYPES.MARKDOWN,
        sourceFormat: 'markdown',
        title,
        summary: summarizeText(text, 320),
        rawText: text,
        characters,
        worldInfo,
        scenario,
        styleHints: {
            headings: sections.slice(0, 12).map(section => section.heading),
        },
        metadata: {
            filename: file.name,
            mimeType: file.type || '',
            parser: 'markdown_adapter',
            importedAt: new Date().toISOString(),
            sectionCount: sections.length,
        },
        importWarnings: [],
        rawSource: {
            sections,
        },
    };
};

const parseTextImport = async (file) => {
    const text = await file.text();
    const title = filenameWithoutExtension(file.name);

    return {
        sourceType: IMPORT_SOURCE_TYPES.TEXT,
        sourceFormat: 'plain_text',
        title,
        summary: summarizeText(text, 320),
        rawText: text,
        characters: [],
        worldInfo: [],
        scenario: '',
        styleHints: {},
        metadata: {
            filename: file.name,
            mimeType: file.type || '',
            parser: 'text_adapter',
            importedAt: new Date().toISOString(),
            characterCount: text.length,
        },
        importWarnings: [],
        rawSource: {
            text,
        },
    };
};

const parsePdfImport = async () => {
    throw new Error('PDF import is not implemented yet. The import flow is ready for it, but this adapter still needs text extraction support.');
};

export const buildImportDraftFromFile = async (file) => {
    if (!file) {
        throw new Error('Please choose a file to import.');
    }

    const sourceType = inferSourceType(file);

    switch (sourceType) {
        case IMPORT_SOURCE_TYPES.CHARACTER_CARD:
            return parseCharacterCardImport(file);
        case IMPORT_SOURCE_TYPES.MARKDOWN:
            return parseMarkdownImport(file);
        case IMPORT_SOURCE_TYPES.TEXT:
            return parseTextImport(file);
        case IMPORT_SOURCE_TYPES.PDF:
            return parsePdfImport(file);
        default:
            throw new Error(`Unsupported import source type: ${sourceType}`);
    }
};
