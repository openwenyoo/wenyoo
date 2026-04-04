(function () {
    const PARENT_ORIGIN = window.location.origin;

    class StoryBridge {
        constructor() {
            this.handlers = new Map();
            this.latestInit = null;
            window.addEventListener('message', (event) => {
                if (event.origin !== PARENT_ORIGIN) return;
                const message = event.data || {};
                if (message.type === 'wenyoo:init') {
                    this.latestInit = message.payload || {};
                    this._emit('init', this.latestInit);
                    return;
                }
                if (message.type === 'wenyoo:event') {
                    this._emit('event', message.payload);
                    const payload = message.payload || {};
                    if (payload.type) {
                        this._emit(payload.type, payload);
                    }
                }
            });
        }

        on(eventName, handler) {
            if (!this.handlers.has(eventName)) {
                this.handlers.set(eventName, new Set());
            }
            this.handlers.get(eventName).add(handler);
            return () => this.handlers.get(eventName)?.delete(handler);
        }

        _emit(eventName, payload) {
            const handlers = this.handlers.get(eventName);
            if (!handlers) return;
            handlers.forEach((handler) => {
                try {
                    handler(payload);
                } catch (error) {
                    console.error(`Wenyoo story SDK handler failed for ${eventName}:`, error);
                }
            });
        }

        _post(type, payload) {
            window.parent.postMessage({ type, payload }, PARENT_ORIGIN);
        }

        _postHost(action, payload = {}) {
            window.parent.postMessage({
                type: 'wenyoo:host',
                payload: { action, ...payload },
            }, PARENT_ORIGIN);
        }

        dispatchAction(actionId, payload = {}, options = {}) {
            this._post('wenyoo:dispatch', {
                type: 'ui_action',
                action_id: actionId,
                payload,
                ...options,
            });
        }

        query(query, payload = {}) {
            this._post('wenyoo:dispatch', {
                type: 'ui_query',
                query,
                payload,
            });
        }

        submitForm(formId, data = {}, files = {}) {
            this.dispatchAction('form_submit', {
                form_id: formId,
                data,
                files,
            }, {
                execution: 'form_submit',
            });
        }

        sendDeterministicAction(actionId, payload = {}, options = {}) {
            this.dispatchAction(actionId, payload, {
                execution: 'deterministic_action',
                ...options,
            });
        }

        sendArchitectTask(taskType, options = {}) {
            this.dispatchAction(options.action_id || taskType, options.payload || {}, {
                execution: 'architect_action',
                task: {
                    task_type: taskType,
                    task_profile: options.task_profile,
                    player_input: options.player_input,
                    purpose: options.purpose,
                    structured_input: options.structured_input || options.payload || {},
                    expected_output: options.expected_output,
                    delivery_policy: options.delivery_policy,
                    extra_context: options.extra_context || {},
                    action_hint: options.action_hint || '',
                    input_type: options.input_type || 'story_app',
                    node_id: options.node_id,
                    event_context: options.event_context,
                    form_data: options.form_data,
                },
                display_text: options.display_text,
                action_hint: options.action_hint,
                input_type: options.input_type || 'story_app',
                expected_output: options.expected_output,
                task_profile: options.task_profile,
                delivery_policy: options.delivery_policy,
                purpose: options.purpose,
            });
        }

        requestInitialState() {
            this.query('initial_state');
        }

        requestPerception() {
            this.query('current_perception');
        }

        requestReturnToMenu() {
            this._postHost('return_to_menu');
        }

        sendRaw(message) {
            this._post('wenyoo:dispatch', message);
        }
    }

    window.WenyooStorySDK = {
        createBridge() {
            return new StoryBridge();
        },
    };
})();
