/** @odoo-module **/
import { Component } from "@odoo/owl";
import { MailSearch } from "../mail_search/mail_search.esm.js";

export class MailList extends Component {
    static template = "user_mail_imap.MailList";
    static components = { MailSearch };
    static props = {
        messages: { type: Array, optional: true },
        total: Number,
        loading: Boolean,
        // `optional: true` only allows `undefined`. The store sets this to
        // `null` when no message is selected, so the type must accept `null`
        // explicitly — otherwise OWL's dev-mode prop validation throws.
        selectedMessage: { type: [Object, { value: null }], optional: true },
        currentFolder: String,
        // IMAP-fel för aktuell mapp (t.ex. avvisat SELECT). Renderas som en
        // varning i listan i stället för en tyst tom mapp.
        folderError: { type: [String, { value: null }], optional: true },
        searchActive: { type: Boolean, optional: true },
        searchQuery: { type: String, optional: true },
        searchTotal: { type: Number, optional: true },
        onSearch: Function,
        onClearSearch: Function,
        onMessageClick: Function,
        loadMore: Function,
        openComposer: Function,
        // Flaggning och flaggfilter. `onToggleFlag` sätter/ta bort en
        // flagga på ett enskilt mail; `flagFilter` filtrerar listan på
        // flaggtyp ('' = alla).
        onToggleFlag: Function,
        flagFilter: { type: String, optional: true },
        onSetFlagFilter: Function,
        // Trådad visning. `threaded` slår på grupperingen; trådens
        // hopfällning ligger per tråd i `msg.threadCollapsed`.
        threaded: { type: Boolean, optional: true },
        onToggleThreaded: Function,
        onToggleThread: Function,
        // "Skapa regel" i listhuvudet — samma dialog som i meddelandevyn,
        // men nåbar utan att först öppna ett mail.
        openRuleDialog: Function,
    };

    /**
     * Flaggtyperna, i samma ordning som i regeldialogen.
     *
     * `flagged`/`important` är standardflaggor (RFC 3501) som syns i alla
     * klienter. `todo`/`personal`/`work` är IMAP-nyckelord — samma
     * märkning Thunderbird använder. `spam` sätts som Junk-nyckelord.
     */
    get flagOptions() {
        return [
            { value: 'flagged', label: 'Stjärnmärkta', icon: 'fa-star text-warning' },
            { value: 'important', label: 'Viktiga', icon: 'fa-check-circle text-success' },
            { value: 'spam', label: 'Skräppost', icon: 'fa-ban text-danger' },
            { value: 'todo', label: 'Att göra', icon: 'fa-tasks text-primary' },
            { value: 'personal', label: 'Privat', icon: 'fa-user text-info' },
            { value: 'work', label: 'Arbete', icon: 'fa-briefcase text-secondary' },
        ];
    }

    flagIcon(value) {
        const opt = this.flagOptions.find((o) => o.value === value);
        return opt ? opt.icon : 'fa-star-o';
    }

    flagLabel(value) {
        const opt = this.flagOptions.find((o) => o.value === value);
        return opt ? opt.label : 'Alla mail';
    }

    /**
     * Klick på stjärnan ska INTE välja mailet.
     *
     * Raden har en klickhanterare som öppnar meddelandet. Utan
     * stopPropagation skulle ett stjärnklick både markera mailet och byta
     * det valda meddelandet — användaren tappar sin plats i listan för att
     * hen ville stjärnmärka något annat.
     */
    onStarClick(ev, msg) {
        ev.stopPropagation();
        this.props.onToggleFlag(msg, !msg.flagged);
    }
}
