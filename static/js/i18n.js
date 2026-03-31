(function () {
    const STORAGE_KEY = 'textAdventure.locale';

    const messages = {
        en: {
            'document.title': 'Wenyoo',
            'welcome.loading': 'loading...',
            'player.namePrompt': 'Please Input Your Name',
            'player.namePlaceholder': 'input your name...',
            'player.confirm': 'Confirm',
            'story.selectTitle': 'Select Your Adventure',
            'story.selectSubtitle': 'Choose your adventure.',
            'story.stories': 'Stories',
            'session.kicker': 'Continue or start a session',
            'session.title': 'Choose how to play',
            'session.sessionsArea': 'Sessions',
            'session.mySessions': 'Saved Sessions',
            'session.joinByCode': 'Join a Room',
            'session.create': 'Start New Session',
            'session.yourSessions': 'Your sessions',
            'session.emptyForStory': 'No resumable sessions for this story yet.',
            'session.codePlaceholder': 'Enter room code',
            'session.join': 'Join Session',
            'panel.info': 'Info',
            'panel.settings': 'Settings',
            'settings.gameCode': 'Session Code',
            'settings.language': 'Language',
            'settings.languageEnglish': 'English',
            'settings.languageChinese': 'Chinese',
            'settings.copyTitle': 'Copy to clipboard',
            'settings.copy': 'Copy',
            'settings.typewriter': 'Typewriter Effect',
            'settings.saveGame': 'Save Game',
            'settings.save': 'Save',
            'settings.exportHistory': 'Export History',
            'settings.export': 'Export',
            'settings.return': 'Return to Menu',
            'settings.reload': 'Reload Game',
            'input.placeholder': 'Type a message, or / for commands...',
            'input.send': 'Send',
            'input.continue': 'Continue',
            'loading.generatingStory': 'Generating story...',
            'loading.objectActions': 'Loading actions',
            'commands.helpDescription': 'Show available slash commands',
            'commands.saveDescription': 'Save the current game',
            'commands.reloadDescription': 'Restart the current story',
            'commands.exportDescription': 'Export the current message history',
            'commands.playersDescription': 'Show the players in this session',
            'commands.statusDescription': 'Toggle the detail panel',
            'commands.helpTitle': 'Slash Commands',
        },
        'zh-CN': {
            'document.title': '文柚',
            'welcome.loading': '加载中...',
            'player.namePrompt': '请输入你的名字',
            'player.namePlaceholder': '输入你的名字...',
            'player.confirm': '确认',
            'story.selectTitle': '选择你的冒险',
            'story.selectSubtitle': '选择一个冒险开始吧。',
            'story.stories': '故事',
            'session.kicker': '继续或开始一个会话',
            'session.title': '选择游玩方式',
            'session.sessionsArea': '会话',
            'session.mySessions': '已保存会话',
            'session.joinByCode': '加入房间',
            'session.create': '开始新会话',
            'session.yourSessions': '你的会话',
            'session.emptyForStory': '这个故事还没有可恢复的会话。',
            'session.codePlaceholder': '输入房间代码',
            'session.join': '加入会话',
            'panel.info': '信息',
            'panel.settings': '设置',
            'settings.gameCode': '会话代码',
            'settings.language': '语言',
            'settings.languageEnglish': '英文',
            'settings.languageChinese': '中文',
            'settings.copyTitle': '复制到剪贴板',
            'settings.copy': '复制',
            'settings.typewriter': '打字机效果',
            'settings.saveGame': '保存游戏',
            'settings.save': '保存',
            'settings.exportHistory': '导出历史',
            'settings.export': '导出',
            'settings.return': '返回菜单',
            'settings.reload': '重新加载游戏',
            'input.placeholder': '输入内容，或输入 / 打开指令...',
            'input.send': '发送',
            'input.continue': '继续',
            'loading.generatingStory': '正在生成故事...',
            'loading.objectActions': '正在加载操作',
            'commands.helpDescription': '显示可用的斜杠指令',
            'commands.saveDescription': '保存当前游戏',
            'commands.reloadDescription': '重新开始当前故事',
            'commands.exportDescription': '导出当前消息历史',
            'commands.playersDescription': '显示当前会话中的玩家',
            'commands.statusDescription': '切换详情面板',
            'commands.helpTitle': '斜杠指令',
        },
    };

    function normalizeLocale(locale) {
        return String(locale || '').toLowerCase().startsWith('zh') ? 'zh-CN' : 'en';
    }

    function getLocale() {
        const saved = window.localStorage.getItem(STORAGE_KEY);
        return normalizeLocale(saved || 'en');
    }

    function translate(key, locale) {
        const resolvedLocale = normalizeLocale(locale || getLocale());
        return messages[resolvedLocale][key] || messages.en[key] || key;
    }

    function setLocale(locale) {
        const normalized = normalizeLocale(locale);
        window.localStorage.setItem(STORAGE_KEY, normalized);
        applyTranslations();
        document.dispatchEvent(new CustomEvent('textAdventure:localeChanged', {
            detail: { locale: normalized }
        }));
        return normalized;
    }

    function translateElement(element, locale) {
        const key = element.getAttribute('data-i18n');
        const placeholderKey = element.getAttribute('data-i18n-placeholder');
        const titleKey = element.getAttribute('data-i18n-title');

        if (key) {
            element.textContent = messages[locale][key] || messages.en[key] || key;
        }

        if (placeholderKey) {
            element.setAttribute('placeholder', messages[locale][placeholderKey] || messages.en[placeholderKey] || placeholderKey);
        }

        if (titleKey) {
            element.setAttribute('title', messages[locale][titleKey] || messages.en[titleKey] || titleKey);
        }
    }

    function applyTranslations() {
        const locale = getLocale();
        document.documentElement.lang = locale;
        document.title = translate('document.title', locale);
        document.querySelectorAll('[data-i18n], [data-i18n-placeholder], [data-i18n-title]').forEach((element) => {
            translateElement(element, locale);
        });
    }

    window.TextAdventureI18n = {
        applyTranslations,
        getLocale,
        normalizeLocale,
        setLocale,
        t: translate,
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', applyTranslations);
    } else {
        applyTranslations();
    }
}());
