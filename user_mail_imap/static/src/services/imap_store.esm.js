/** @odoo-module **/
import { reactive } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";

const store = {
    dependencies: [],
    start(env) {
        // `reactive()` makes the state observable by OWL. All mutations go
        // through this proxy (`state.x = y`); nothing mutates the raw target
        // around it.
        //
        // Note the callback default: `reactive(target, callback = NO_CALLBACK)`.
        // With NO_CALLBACK, `observeTargetKey()` returns immediately, so merely
        // reading this proxy subscribes to nothing. A component must bind the
        // state to its render callback with `useState(this.store.state)` —
        // which re-wraps the *same* raw target with the render callback. See
        // `mail_imap.esm.js` for the full explanation.
        //
        // The previous implementation did `useState(getState())` followed by
        // `Object.assign(proxy, original)` on every notification. That is a
        // no-op: OWL's reactive proxy compares values on write and skips the
        // update when the value is unchanged, and `Object.assign` copies the
        // very same object references back onto the proxy. The view therefore
        // never re-rendered when a message was selected.
        const state = reactive({
            folders: [],
            messages: [],
            selectedMessage: null,
            currentFolder: 'INBOX',
            hasPassword: false,
            passwordError: null,
            totalMessages: 0,
            offset: 0,
            loading: false,
            loadingDetail: false,
            searchQuery: '',
            searchActive: false,
            searchTotal: 0,
        });

        // Cache: store data per folder. Deliberately NOT part of the reactive
        // state: the background preload writes to it without changing what is
        // displayed, and a reactive cache would trigger renders for nothing.
        const folderCache = {};       // folderCache[folder] = { messages, total, offset }
        let foldersCached = null;
        let selectedUid = null;       // Track requested UID to prevent race conditions

        return {
            // The one reactive state object — the single source of truth.
            // Consumers bind it to their render callback:
            // `this.state = useState(this.store.state)`. There is no
            // subscribe/copy pair; `Object.assign` copies are what made the
            // detail view miss updates before.
            state,

            async checkPassword() {
                const res = await rpc('/imap/check');
                state.hasPassword = res.has_password;
                return res.has_password;
            },

            async setPassword(password) {
                // The controller verifies against dovecot_password and
                // answers {error: ...} when the password does not match.
                // Never set hasPassword on failure -- the UI would then
                // claim "Password set" for a password IMAP login rejects.
                const res = await rpc('/imap/set_password', { password });
                if (res && res.error) {
                    state.passwordError = res.error;
                    return false;
                }
                state.passwordError = null;
                state.hasPassword = true;
                return true;
            },

            async loadFolders(force = false) {
                // Serve cached immediately, refresh in background
                if (foldersCached && !force) {
                    state.folders = foldersCached;
                    // Background refresh
                    this._refreshFolders();
                    return foldersCached;
                }
                const folders = await rpc('/imap/folders');
                foldersCached = folders;
                state.folders = folders;
                return folders;
            },

            async _refreshFolders() {
                try {
                    const folders = await rpc('/imap/folders');
                    if (JSON.stringify(folders) !== JSON.stringify(foldersCached)) {
                        foldersCached = folders;
                        state.folders = folders;
                    }
                } catch (e) { /* silent */ }
            },

            async loadMessages(folder, offset = 0) {
                // Always show loading when switching folders
                const switchingFolder = state.currentFolder !== folder;
                if (switchingFolder) {
                    state.loading = true;
                    state.currentFolder = folder;
                    state.selectedMessage = null;
                }

                const cacheKey = folder;
                const cached = folderCache[cacheKey];

                if (offset === 0 && cached) {
                    // Return cached immediately, then background refresh
                    state.messages = cached.messages;
                    state.totalMessages = cached.total;
                    state.offset = cached.offset;
                    state.currentFolder = folder;
                    state.loading = false;
                    this._refreshMessages(folder);
                    // Preload other folders in background
                    this._preloadFolders(folder);
                    return;
                }

                if (offset > 0) {
                    state.loading = true;
                }

                try {
                    const res = await rpc('/imap/mails', { folder, offset, limit: 80 });
                    const messages = offset === 0
                        ? res.messages
                        : [...(cached?.messages || []), ...res.messages];

                    folderCache[cacheKey] = { messages, total: res.total, offset: offset + 80 };
                    // Replace the array wholesale: OWL tracks a new reference
                    // reliably, deep in-place mutations less so.
                    state.messages = messages;
                    state.totalMessages = res.total;
                    state.offset = offset + 80;
                    state.currentFolder = folder;
                    state.loading = false;
                    // Preload other folders in background
                    this._preloadFolders(folder);
                } catch (e) {
                    state.loading = false;
                }
            },

            async _preloadFolders(excludeFolder) {
                // Preload 25 messages from other folders in background
                if (!foldersCached) return;
                const toPreload = foldersCached
                    .filter(f => f.name !== excludeFolder && !folderCache[f.name])
                    .slice(0, 3); // preload max 3 other folders
                for (const f of toPreload) {
                    try {
                        const res = await rpc('/imap/mails', { folder: f.name, offset: 0, limit: 25 });
                        folderCache[f.name] = { messages: res.messages, total: res.total, offset: 25 };
                    } catch (e) { /* silent */ }
                }
            },

            async _refreshMessages(folder) {
                try {
                    const res = await rpc('/imap/mails', { folder, offset: 0, limit: 80 });
                    const cached = folderCache[folder];
                    if (!cached || JSON.stringify(res.messages) !== JSON.stringify(cached.messages)) {
                        folderCache[folder] = { messages: res.messages, total: res.total, offset: 50 };
                        if (state.currentFolder === folder) {
                            state.messages = res.messages;
                            state.totalMessages = res.total;
                            state.offset = 50;
                        }
                    }
                } catch (e) { /* silent */ }
            },

            /**
             * Search the whole folder on the server (IMAP SEARCH), not just the
             * messages already loaded in the list.
             *
             * @param {string} query   free-text query; empty clears the search
             * @param {string} folder  folder to search, defaults to the current one
             * @param {number} offset  pagination offset
             */
            async searchMails(query, folder = null, offset = 0) {
                const targetFolder = folder || state.currentFolder;
                const term = (query || '').trim();

                if (!term) {
                    // Clearing the search restores the normal folder listing.
                    state.searchQuery = '';
                    state.searchActive = false;
                    state.searchTotal = 0;
                    await this.loadMessages(targetFolder, 0);
                    return;
                }

                if (offset === 0) {
                    state.loading = true;
                    state.currentFolder = targetFolder;
                    state.searchQuery = term;
                    state.searchActive = true;
                    state.selectedMessage = null;
                }

                try {
                    const res = await rpc('/imap/search', {
                        folder: targetFolder,
                        query: term,
                        offset,
                        limit: 80,
                    });
                    const messages = offset === 0
                        ? res.messages
                        : [...state.messages, ...res.messages];
                    state.messages = messages;
                    state.totalMessages = res.total;
                    state.searchTotal = res.total;
                    state.offset = offset + 80;
                    state.loading = false;
                } catch (e) {
                    state.loading = false;
                    state.messages = [];
                    state.totalMessages = 0;
                    state.searchTotal = 0;
                }
            },

            /** Clear an active search and return to the folder listing. */
            async clearSearch() {
                await this.searchMails('', state.currentFolder, 0);
            },

            async loadMail(folder, uid) {
                // Track the requested UID to prevent out-of-order responses
                const requestUid = uid;
                selectedUid = requestUid;
                state.loadingDetail = true;

                try {
                    const msg = await rpc('/imap/mail', { folder, uid });
                    // Only apply if this is still the latest request
                    if (selectedUid === requestUid) {
                        state.selectedMessage = msg;
                        state.loadingDetail = false;
                    }
                } catch (e) {
                    if (selectedUid === requestUid) {
                        state.loadingDetail = false;
                    }
                }
            },

            async sendMail(to, subject, body, cc) {
                await rpc('/imap/send', { to, subject, body, cc });
            },

            async setFlag(folder, uids, flag, value) {
                await rpc('/imap/flag', { folder, uids, flag, value });
                // Invalidate cache
                delete folderCache[folder];
            },

            async fetchTemplates() {
                const res = await rpc('/imap/templates');
                return res.templates || [];
            },

            async renderTemplate(templateId) {
                return await rpc('/imap/template/render', { template_id: templateId });
            },

            async searchPartners(query) {
                const res = await rpc('/imap/partners', { query });
                return res.partners || [];
            },

            async sync() {
                await rpc('/imap/sync');
                this.invalidateCache();
            },

            invalidateCache() {
                for (const key of Object.keys(folderCache)) {
                    delete folderCache[key];
                }
                foldersCached = null;
            },

            invalidateFolderCache() {
                for (const key of Object.keys(folderCache)) {
                    delete folderCache[key];
                }
                foldersCached = null;
            },
        };
    },
};

registry.category("services").add("user_mail_imap.store", store);
