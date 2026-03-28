import axios from 'axios';

/**
 * Read the editor secret from the query-string (?editor_token=...) or
 * from localStorage. The query-string takes precedence so operators can
 * share a bookmarkable URL.
 */
function getEditorToken() {
    const params = new URLSearchParams(window.location.search);
    const fromUrl = params.get('editor_token');
    if (fromUrl) {
        localStorage.setItem('editorToken', fromUrl);
        return fromUrl;
    }
    return localStorage.getItem('editorToken') || '';
}

const editorToken = getEditorToken();

// Axios interceptor — attaches X-Editor-Token to every request.
axios.interceptors.request.use((config) => {
    if (editorToken) {
        config.headers['X-Editor-Token'] = editorToken;
    }
    return config;
});

/**
 * Wrapper around fetch() that adds the editor auth header.
 * Drop-in replacement: editorFetch(url, init) has the same API as fetch().
 */
export function editorFetch(url, init = {}) {
    if (editorToken) {
        init.headers = {
            ...(init.headers || {}),
            'X-Editor-Token': editorToken,
        };
    }
    return fetch(url, init);
}
