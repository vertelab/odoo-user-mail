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
            // Satt när ett IMAP-anrop misslyckas. Utan den här visas en tom
            // mapp som om den vore tom — ett avvisat SELECT (t.ex. ett
            // mappnamn med mellanslag som skickats ociterat) svaldes tidigare
            // helt av `catch (e) { state.loading = false; }`.
            folderError: null,
            searchQuery: '',
            searchActive: false,
            // Flaggfilter: '' = alla, annars en flaggtyp
            // (flagged/important/spam/todo/personal/work).
            //
            // Filtret körs på SERVERN över hela mappen (se applyView), inte
            // över den hämtade sidan. Klient-side filtrering hittade bara
            // stjärnmärkta mail bland de ~80 som redan var laddade, så en
            // träff på plats 412 svarade "inga mail med den flaggan".
            flagFilter: '',
            // Oläst är en EGEN axel, inte en sjunde flagga: `seen` styr
            // fetstil och läses av servern som UNSEEN. Att lägga den i
            // flagglistan skulle göra "oläst" till en etikett man sätter på
            // ett mail och ge två vägar till samma serverfält.
            unreadFilter: false,
            // Trådad visning. Klient-side över den hämtade sidan — se
            // threadMessages i mail_imap.esm.js.
            threaded: false,
            collapsedThreads: new Set(),
            threadedCount: 0,
            threadScanned: 0,
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
                    state.folderError = null;
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
                    // Visa felet i stället för en tyst tom mapp. Odoo:s RPC
                    // kastar ett fel vars `data.message` bär UserError-texten
                    // från `_select_folder()`.
                    state.folderError = (
                        (e && e.data && e.data.message) ||
                        (e && e.message) ||
                        'Kunde inte hämta mappen.'
                    );
                    state.messages = [];
                    state.totalMessages = 0;
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
             * En vyladdning: sökord + flagga + oläst i ETT anrop.
             *
             * Det finns en enda väg till servern för "vad listan visar"
             * (`applyView`), i stället för separata `searchMails` /
             * `filterMails` / `setUnread` som var och en satte sin egen del
             * av state. Skälet är subtilt men avgörande: `total` och
             * `offset` beskriver HELA resultatmängden, och delade anrop
             * kunde inte veta om det andra filtret var aktivt — så `total`
             * blev fel och pagineringen hoppade. Tre predikat i en fråga
             * ger linjärt många testfall i stället för multiplicerade.
             *
             * Server-side betyder dessutom att filtret täcker hela mappen,
             * inte de ~80 mail som råkade vara laddade.
             *
             * @param {object}  opts
             * @param {string} [opts.query]   fritext; tom + filter = filtrera
             * @param {string} [opts.flag]    flaggtyp eller '' för alla
             * @param {boolean}[opts.unread]  bara olästa
             * @param {number} [opts.offset]  paginering
             * @param {string} [opts.folder]  mapp, default aktuell
             */
            async applyView({ query, flag, unread, offset = 0, folder } = {}) {
                const targetFolder = folder || state.currentFolder;
                const term = (query !== undefined
                    ? (query || '')
                    : (state.searchActive ? state.searchQuery : '')).trim();
                const flagFilter = (flag !== undefined ? (flag || '') : state.flagFilter);
                const unreadFilter = (unread !== undefined
                    ? !!unread : !!state.unreadFilter);
                const filtered = !!(flagFilter || unreadFilter);

                if (offset === 0) {
                    state.loading = true;
                    state.currentFolder = targetFolder;
                    state.selectedMessage = null;
                    state.searchQuery = term;
                    state.searchActive = !!term;
                    state.flagFilter = flagFilter;
                    state.unreadFilter = unreadFilter;
                    if (!term && !filtered) {
                        state.searchTotal = 0;
                    }
                }

                // Ingen sökning, inget filter -> den vanliga mapplistningen.
                // Går via loadMessages så mappcachen och bakgrundsuppdateringen
                // används som förut.
                if (!term && !filtered) {
                    await this.loadMessages(targetFolder, offset);
                    return;
                }

                try {
                    // Ett filter utan sökord är ett filter, inte en sökning —
                    // men servern svarar på båda via samma metod, så klienten
                    // behöver bara välja rätt rutt.
                    const route = term ? '/imap/search' : '/imap/filter';
                    const limit = 80;
                    const res = await rpc(route, {
                        folder: targetFolder,
                        query: term,
                        flag: flagFilter || null,
                        unread: unreadFilter,
                        offset,
                        limit,
                    });
                    const messages = offset === 0
                        ? res.messages
                        : [...state.messages, ...res.messages];
                    state.messages = messages;
                    state.totalMessages = res.total;
                    state.searchTotal = res.total;
                    // Sidstorleken får inte hårdkodas här: rutternas default
                    // är 50, och en avvikelse hade tystat tappat 30 mail per
                    // "visa fler".
                    state.offset = offset + limit;
                    state.loading = false;
                } catch (e) {
                    state.loading = false;
                    // Behåll inte gamla rader: de hör till föregående vy och
                    // ser ut som träffar på det nya filtret.
                    state.messages = [];
                    state.totalMessages = 0;
                    state.searchTotal = 0;
                    state.folderError = (
                        (e && e.data && e.data.message) ||
                        (e && e.message) ||
                        'Kunde inte söka i mappen.'
                    );
                }
            },

            /** Sätt flaggfilter och ladda om vyn (server-side). */
            async setFlagFilter(flag) {
                await this.applyView({ flag: flag || '', offset: 0 });
            },

            /** Slå på/av olästfiltret och ladda om vyn (server-side). */
            async setUnreadFilter(unread) {
                await this.applyView({ unread: !!unread, offset: 0 });
            },

            /**
             * Search the whole folder on the server (IMAP SEARCH), not just the
             * messages already loaded in the list.
             *
             * Behåller flagg- och olästfiltret: en sökning ska begränsa det
             * man redan filtrerat, inte nollställa det.
             *
             * @param {string} query   free-text query; empty clears the search
             * @param {string} folder  folder to search, defaults to the current one
             * @param {number} offset  pagination offset
             */
            async searchMails(query, folder = null, offset = 0) {
                await this.applyView({ query, folder, offset });
            },

            /** Clear an active search and return to the folder listing. */
            async clearSearch() {
                // Rensar sökordet men behåller aktiva filter — att tömma
                // sökfältet ska inte tysta släppa flagg-/olästfiltret.
                await this.applyView({ query: '', offset: 0 });
            },

            async loadMail(folder, uid) {
                // Track the requested UID to prevent out-of-order responses
                const requestUid = uid;
                selectedUid = requestUid;
                state.loadingDetail = true;

                // R4: ett mail som öppnas markeras läst på servern (BODY
                // utan PEEK), och faller då ur ett aktivt olästfilter. Här
                // hämtas BARA detaljen — listan laddas inte om — så raden
                // ligger kvar under läsningen och listan hoppar inte för
                // användaren. Den lämnar filtret först vid nästa vyladdning
                // (applyView), vilket är korrekt men ska inte ske mid-read.
                // Ändra inte detta till en omladdning av listan här.
                try {
                    const msg = await rpc('/imap/mail', { folder, uid });
                    // Only apply if this is still the latest request
                    if (selectedUid === requestUid) {
                        state.selectedMessage = msg;
                        state.loadingDetail = false;
                        // Håll listans rad i takt med detaljen: servern
                        // markerade mailet läst, och fetstilen ska släppa
                        // direkt — men raden ska inte tas bort ur listan.
                        const row = (state.messages || []).find(
                            (m) => m.uid === uid);
                        if (row && msg && msg.seen) {
                            row.seen = true;
                        }
                    }
                } catch (e) {
                    if (selectedUid === requestUid) {
                        state.loadingDetail = false;
                    }
                }
            },

            /**
             * Trådar från servern.
             *
             * Skiljer sig från loadMessages: servern slår upp hela tråden
             * med SEARCH, så även delar utanför den hämtade sidan följer
             * med. Klient-side gruppering kunde bara se det som redan
             * hämtats, och i en stor mapp är det nästan aldrig både
             * förälder och svar i samma fönster.
             */
            async loadThreads(folder = null, offset = 0) {
                const targetFolder = folder || state.currentFolder;
                if (offset === 0) {
                    state.loading = true;
                    state.currentFolder = targetFolder;
                }
                try {
                    const res = await rpc('/imap/threads', {
                        folder: targetFolder,
                        offset,
                        limit: 40,
                    });
                    const threads = res.threads || [];
                    // Platta ut till listrader: trådens nyaste meddelande
                    // blir raden, resten hänger på den.
                    const rows = threads.map((t) => {
                        const newest = t.messages[0];
                        return {
                            ...newest,
                            threadRoot: t.root,
                            threadCount: t.messages.length,
                            threadMessages: t.messages,
                            threadCollapsed: state.collapsedThreads.has(t.root),
                        };
                    });
                    state.messages = offset === 0
                        ? rows
                        : state.messages.concat(rows);
                    state.total = res.total || rows.length;
                    state.offset = offset;
                    // Hur många trådar som faktiskt har fler än ett
                    // meddelande. Utan siffran ser en inkorg med mest
                    // nyhetsbrev ut som att trådning inte fungerar.
                    state.threadedCount = res.threaded_count || 0;
                    state.threadScanned = res.scanned || 0;
                } finally {
                    state.loading = false;
                }
            },

            async sendMail(to, subject, body, cc, attachments) {
                await rpc('/imap/send', { to, subject, body, cc, attachments });
            },

            async setFlag(folder, uids, flag, value) {
                await rpc('/imap/flag', { folder, uids, flag, value });
                // Invalidate cache
                delete folderCache[folder];
            },

            /**
             * Mapparna bakom Arkivera / Skräppost / Ta bort.
             *
             * Slås upp en gång per session och cachas: de ändras inte, och
             * ett LIST-anrop per knapptryck vore slöseri.
             */
            async specialFolders() {
                if (!folderCache.__special) {
                    folderCache.__special = await rpc('/imap/special_folders', {});
                }
                return folderCache.__special;
            },

            /**
             * Flytta meddelanden (Arkivera / Skräppost / Ta bort).
             *
             * Cachen för BÅDA mapparna rensas: källmappen för att mailet
             * försvunnit, målmappen för att det dykt upp. Rensas bara
             * källmappen visar målmappen sitt gamla innehåll tills TTL:n
             * går ut.
             */
            async moveMails(folder, uids, toFolder) {
                await rpc('/imap/move', { folder, uids, to_folder: toFolder });
                delete folderCache[folder];
                delete folderCache[toFolder];
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
