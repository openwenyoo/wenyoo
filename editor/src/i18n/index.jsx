import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { messages } from './messages';

export const LOCALE_STORAGE_KEY = 'textAdventure.locale';
const DEFAULT_LOCALE = 'en';
const ZH_LOCALE = 'zh-CN';
const SUPPORTED_LOCALES = [DEFAULT_LOCALE, ZH_LOCALE];

const LocaleContext = createContext(null);

function normalizeLocale(locale) {
    if (!locale) {
        return DEFAULT_LOCALE;
    }

    const normalized = String(locale).trim().toLowerCase();
    if (normalized.startsWith('zh')) {
        return ZH_LOCALE;
    }

    return DEFAULT_LOCALE;
}

function getInitialLocale() {
    if (typeof window === 'undefined') {
        return DEFAULT_LOCALE;
    }

    const savedLocale = window.localStorage.getItem(LOCALE_STORAGE_KEY);
    if (savedLocale) {
        return normalizeLocale(savedLocale);
    }

    return normalizeLocale(window.navigator?.language);
}

function formatMessage(template, variables = {}) {
    return String(template).replace(/\{(\w+)\}/g, (_, key) => {
        const value = variables[key];
        return value === undefined || value === null ? `{${key}}` : String(value);
    });
}

function getMessage(locale, key) {
    return messages[locale]?.[key] ?? messages[DEFAULT_LOCALE]?.[key] ?? key;
}

export function LocaleProvider({ children }) {
    const [locale, setLocaleState] = useState(getInitialLocale);

    useEffect(() => {
        if (typeof window === 'undefined') {
            return;
        }

        window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
        document.documentElement.lang = locale;
    }, [locale]);

    const value = useMemo(() => ({
        locale,
        locales: SUPPORTED_LOCALES,
        setLocale: (nextLocale) => setLocaleState(normalizeLocale(nextLocale)),
        t: (key, variables) => formatMessage(getMessage(locale, key), variables),
    }), [locale]);

    return (
        <LocaleContext.Provider value={value}>
            {children}
        </LocaleContext.Provider>
    );
}

export function useLocale() {
    const context = useContext(LocaleContext);
    if (!context) {
        throw new Error('useLocale must be used within a LocaleProvider');
    }
    return context;
}

export { normalizeLocale };
