/** @odoo-module **/
import { Component } from "@odoo/owl";
import { MailSearch } from "../mail_search/mail_search.esm.js";
import {
    FLAG_OPTIONS, flagIcon, flagLabel,
} from "../../js/mail_flags.esm.js";

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
        // Olästfiltret — egen axel, inte en sjunde flagga. `unreadFilter`
        // är på/av; servern frågar på UNSEEN.
        unreadFilter: { type: Boolean, optional: true },
        onToggleUnreadFilter: Function,
        // Trådad visning. `threaded` slår på grupperingen; trådens
        // hopfällning ligger per tråd i `msg.threadCollapsed`.
        threaded: { type: Boolean, optional: true },
        threadedCount: { type: Number, optional: true },
        threadScanned: { type: Number, optional: true },
        onToggleThreaded: Function,
        onToggleThread: Function,
        // "Skapa regel" i listhuvudet — samma dialog som i meddelandevyn,
        // men nåbar utan att först öppna ett mail.
        openRuleDialog: Function,
    };

    /**
     * Flaggtyperna, delade med meddelandevyns etikettmeny (se
     * js/mail_flags.esm.js). Kopierar man listan här glider de isär.
     */
    get flagOptions() {
        return FLAG_OPTIONS;
    }

    flagIcon(value) {
        return flagIcon(value);
    }

    flagLabel(value) {
        return flagLabel(value);
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
