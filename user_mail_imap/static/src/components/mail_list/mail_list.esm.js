/** @odoo-module **/
import { Component } from "@odoo/owl";

export class MailList extends Component {
    static template = "user_mail_imap.MailList";
    static props = {
        messages: { type: Array, optional: true },
        total: Number,
        loading: Boolean,
        // `optional: true` only allows `undefined`. The store sets this to
        // `null` when no message is selected, so the type must accept `null`
        // explicitly — otherwise OWL's dev-mode prop validation throws.
        selectedMessage: { type: [Object, { value: null }], optional: true },
        currentFolder: String,
        searchActive: { type: Boolean, optional: true },
        onMessageClick: Function,
        loadMore: Function,
        openComposer: Function,
    };
}
