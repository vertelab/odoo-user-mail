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
    };
}
