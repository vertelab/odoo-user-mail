/** @odoo-module **/
import { Component, useState, onWillStart, useRef } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { FolderTree } from "../components/folder_tree/folder_tree.esm.js";
import { MailList } from "../components/mail_list/mail_list.esm.js";
import { MailDetail } from "../components/mail_detail/mail_detail.esm.js";
import { Composer } from "../components/composer/composer.esm.js";
import { SieveRuleDialog } from "../components/sieve_rule_dialog/sieve_rule_dialog.esm.js";

class MailImap extends Component {
    static template = "user_mail_imap.MailImap";
    static components = { FolderTree, MailList, MailDetail, Composer, SieveRuleDialog };
    static props = { ...standardActionServiceProps };

    setup() {
        this.store = useService("user_mail_imap.store");
        // Wrap the store's state in useState so that this component's render
        // function is registered as a subscriber.
        //
        // The store creates its state with `reactive({...})` and no callback.
        // In OWL 2, `reactive()` with no callback uses NO_CALLBACK, and
        // `observeTargetKey()` returns immediately for NO_CALLBACK — so merely
        // reading `this.store.state` subscribes to nothing. Writes to the store
        // then update the data without re-rendering: the mail list, the detail
        // pane and the search results all stayed stale until the component was
        // recreated (leaving the view and coming back).
        //
        // `useState(reactive(x))` returns a proxy over the *same* underlying
        // target but bound to this component's render callback, which is the
        // pattern Odoo core uses (`this.ui = useState(useService("ui"))`).
        this.state = useState(this.store.state);
        this.showComposer = useState({ visible: false, type: 'new', message: null });
        // Dialogen öppnas via dialogService, inte genom att rendera <Dialog>
        // i mallen. Odoos Dialog-komponent gör `useState(this.env.dialogData)`
        // i sin setup, och `dialogData` sätts bara av dialogService. Renderas
        // den direkt blir värdet undefined och useState kastar
        // "Cannot make the given value reactive" — vilket dödar hela
        // webbklienten, inte bara dialogen.
        this.dialog = useService("dialog");
        this.passwordInput = useRef("passwordInput");
        this.mailListContainer = useRef("mailListContainer");
        this._resizeActive = false;

        onWillStart(async () => {
            await this.store.checkPassword();
            if (this.state.hasPassword) {
                await this.store.loadFolders();
                await this.store.loadMessages('INBOX');
            }
        });
    }

    openPasswordPrompt() {
        this.state.showPasswordPrompt = true;
    }

    onPasswordKeydown(ev) {
        if (ev.key === 'Enter') {
            this.onSetPassword(ev.target.value);
        }
    }

    onPasswordButtonClick() {
        this.onSetPassword(this.passwordInput.el.value);
    }

    async onSetPassword(password) {
        await this.store.setPassword(password);
        this.state.showPasswordPrompt = false;
        await this.store.loadFolders();
        await this.store.loadMessages('INBOX');
    }

    async onFolderClick(folder) {
        // Switching folder cancels any active search.
        this.state.searchQuery = '';
        this.state.searchActive = false;
        this.state.searchTotal = 0;
        this.state.currentFolder = folder;
        this.state.selectedMessage = null;
        await this.store.loadMessages(folder, 0);
    }

    async onSearch(query) {
        await this.store.searchMails(query, this.state.currentFolder, 0);
    }

    async onClearSearch() {
        await this.store.clearSearch();
    }

    loadMore() {
        if (this.state.loading) {
            return;
        }
        if (this.state.searchActive) {
            this.store.searchMails(this.state.searchQuery, this.state.currentFolder, this.state.offset);
        } else {
            this.store.loadMessages(this.state.currentFolder, this.state.offset);
        }
    }

    async onMessageClick(uid) {
        await this.store.loadMail(this.state.currentFolder, uid);
    }

    /**
     * Stjärnmärk eller avstjärna ett mail.
     *
     * Flaggan sätts på servern först och därefter i den lokala listan.
     * Ordningen är medveten: misslyckas IMAP-anropet ska stjärnan inte
     * ändras i UI:t — annars visar listan ett läge som servern inte har,
     * och nästa omladdning tar tillbaka den utan förklaring.
     */
    async onToggleFlag(msg, value) {
        try {
            await this.store.setFlag(this.state.currentFolder, [msg.uid], 'flagged', value);
            msg.flagged = value;
            // Det valda meddelandet kan vara samma post — håll dem i takt.
            if (this.state.selectedMessage && this.state.selectedMessage.uid === msg.uid) {
                this.state.selectedMessage.flagged = value;
            }
        } catch (e) {
            this.state.folderError = `Kunde inte stjärnmärka: ${e.message || e}`;
        }
    }

    /**
     * Flaggfilter. Filtrerar den REDAN hämtade sidan i klienten.
     *
     * Ett server-side-filter (`SEARCH KEYWORD TODO`) hade varit riktigare
     * för stora mappar, men kräver en egen sökväg genom cachen och
     * pagineringen. Filtret här är avsett som en snabb vy av det man ser —
     * flaggade mail längre bak i mappen kräver fortfarande att man
     * scrollar eller söker.
     */
    onSetFlagFilter(value) {
        this.state.flagFilter = value || '';
    }

    /**
     * Listan efter stjärnfiltret.
     *
     * METOD, inte getter. En getter anropas implicit av OWL:s
     * template-motor, som då försöker göra returvärdet reaktivt — och en
     * färsk array av redan proxade objekt går inte att wrappa om. Det gav
     * "Cannot make the given value reactive" och hela klienten dog.
     *
     * Anropas explicit från mallen: messages="this.visibleMessages()".
     */
    visibleMessages() {
        const msgs = this.state.messages || [];
        const want = this.state.flagFilter;
        const filtered = want
            ? msgs.filter((m) => (m.flags || []).includes(want))
            : msgs;
        // Trådningen görs på servern (loadThreads) — här behövs bara
        // flaggfiltret. Att gruppera igen i klienten skulle bara se de
        // meddelanden som redan hämtats, vilket var hela problemet.
        return filtered;
    }

    /**
     * Gruppera meddelanden i trådar.
     *
     * Trådning sker i klienten över den hämtade sidan. Det är en
     * medveten begränsning: en riktig trådning kräver att hela mappen
     * hämtas (IMAP har inget tråd-kommando som fungerar mot paginering),
     * och för en inkorg på 10 000 mail är det fel pris att betala för en
     * vy. En tråd vars äldre delar ligger på en annan sida visas därför
     * som en ensam rad — den är inte trasig, den är bara delvis hämtad.
     *
     * Nyckeln är References-kedjans första id (trådens rot) om den finns,
     * annars In-Reply-To, annars meddelandets eget Message-ID. Att bara
     * använda In-Reply-To hade gett en ny tråd per svar — exakt det man
     * vill undvika.
     *
     * Tråden representeras av sitt NYASTE meddelande: listan sorteras
     * nyaste först, och en tråd hör hemma där dess senaste inlägg är.
     */
    threadMessages(msgs) {
        const byRoot = new Map();
        for (const m of msgs) {
            const root = this._threadRoot(m);
            if (!byRoot.has(root)) {
                byRoot.set(root, []);
            }
            byRoot.get(root).push(m);
        }
        const out = [];
        for (const [root, group] of byRoot) {
            // Nyaste först inom tråden.
            group.sort((a, b) => (b.uid || 0) - (a.uid || 0));
            const newest = group[0];
            out.push({
                ...newest,
                threadCount: group.length,
                threadUids: group.map((g) => g.uid),
                threadMessages: group,
                threadCollapsed: this.state.collapsedThreads.has(root),
                threadRoot: root,
            });
        }
        // Behåll listans ordning: nyaste tråd överst.
        out.sort((a, b) => (b.uid || 0) - (a.uid || 0));
        return out;
    }

    /**
     * Trådens rot-id.
     *
     * References är en lista av "<id>"-strängar, äldst först. Första
     * elementet är trådens början. Meddelanden utan References (första
     * mailet i tråden, eller klienter som inte sätter det) faller tillbaka
     * på In-Reply-To och till sist det egna Message-ID:t.
     */
    _threadRoot(m) {
        const refs = (m.references || '').trim();
        if (refs) {
            const match = refs.match(/<[^>]+>/);
            if (match) {
                return match[0];
            }
        }
        const replyTo = (m.in_reply_to || '').trim();
        if (replyTo) {
            const match = replyTo.match(/<[^>]+>/);
            if (match) {
                return match[0];
            }
        }
        return (m.message_id || `uid:${m.uid}`).trim();
    }

    /** Fäll ihop/veckla ut en tråd. */
    onToggleThread(root) {
        if (this.state.collapsedThreads.has(root)) {
            this.state.collapsedThreads.delete(root);
        } else {
            this.state.collapsedThreads.add(root);
        }
        // Set-mutation syns inte för OWL — byt ut den så vyn ritas om.
        this.state.collapsedThreads = new Set(this.state.collapsedThreads);
    }

    /**
     * Slå på/av trådad visning.
     *
     * Trådarna hämtas från servern — servern kan slå upp hela tråden även
     * när delar ligger utanför den hämtade sidan, vilket klienten inte
     * kan. Därför ett nytt anrop när läget ändras, inte bara en
     * omgruppering av det som redan finns i minnet.
     */
    async onToggleThreaded() {
        this.state.threaded = !this.state.threaded;
        if (this.state.threaded) {
            await this.store.loadThreads(this.state.currentFolder, 0);
        } else {
            await this.store.loadMessages(this.state.currentFolder, 0);
        }
    }
    /**
     * Flytta det valda meddelandet till en specialmapp.
     *
     * Mappnamnet slås upp via RFC 6154 i stället för att hårdkodas — se
     * action_special_folders i imap_server.py. Saknas mappen (t.ex. ingen
     * \\Archive) visas ett fel i stället för att mailet flyttas till en
     * mapp som inte finns och tyst försvinner.
     */
    async moveToSpecial(kind) {
        const msg = this.state.selectedMessage;
        if (!msg) {
            return;
        }
        try {
            const folders = await this.store.specialFolders();
            const target = folders[kind];
            if (!target) {
                this.state.folderError = `Ingen mapp hittades för "${kind}".`;
                return;
            }
            await this.store.moveMails(this.state.currentFolder, [msg.uid], target);
            this.state.selectedMessage = null;
            await this.store.loadMessages(this.state.currentFolder);
        } catch (e) {
            this.state.folderError = `Kunde inte flytta meddelandet: ${e.message || e}`;
        }
    }

    onArchive(msg) {
        return this.moveToSpecial('archive');
    }

    onJunk(msg) {
        return this.moveToSpecial('junk');
    }

    onDelete(msg) {
        return this.moveToSpecial('trash');
    }

    openComposer(type, msg) {
        this.showComposer.visible = true;
        this.showComposer.type = type;
        this.showComposer.message = msg;
    }

    closeComposer() {
        this.showComposer.visible = false;
    }

    openRuleDialog(msg) {
        this.dialog.add(SieveRuleDialog, { message: msg });
    }

    async onSendMail(data) {
        await this.store.sendMail(
            data.to, data.subject, data.body, data.cc, data.attachments || []
        );
        this.closeComposer();
    }

    async onSync() {
        await this.store.sync();
        await this.store.loadFolders(true);
        if (this.state.searchActive) {
            await this.store.searchMails(this.state.searchQuery, this.state.currentFolder, 0);
        } else {
            await this.store.loadMessages(this.state.currentFolder, 0);
        }
    }

    startResize(ev) {
        ev.preventDefault();
        const container = this.mailListContainer.el;
        const startX = ev.clientX;
        const startWidth = container.offsetWidth;

        const onMove = (e) => {
            const newWidth = Math.max(200, Math.min(800, startWidth + (e.clientX - startX)));
            container.style.width = newWidth + 'px';
        };
        const onUp = () => {
            document.removeEventListener('mousemove', onMove);
            document.removeEventListener('mouseup', onUp);
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
        };
        document.addEventListener('mousemove', onMove);
        document.addEventListener('mouseup', onUp);
        document.body.style.cursor = 'col-resize';
        document.body.style.userSelect = 'none';
    }
}

registry.category("actions").add("user_mail_imap.dashboard", MailImap);
