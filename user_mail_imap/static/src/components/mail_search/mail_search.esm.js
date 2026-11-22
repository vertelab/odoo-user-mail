/** @odoo-module **/
import { Component, useState, useRef, onWillUnmount, onWillUpdateProps } from "@odoo/owl";

/**
 * Search field for the IMAP client.
 *
 * The query is sent to the server, which runs an IMAP SEARCH over the whole
 * folder — not just the messages already loaded in the list. Input is
 * debounced so that typing does not open one IMAP connection per keystroke.
 */
export class MailSearch extends Component {
    static template = "user_mail_imap.MailSearch";
    static props = {
        query: { type: String, optional: true },
        active: { type: Boolean, optional: true },
        total: { type: Number, optional: true },
        onSearch: Function,
        onClear: Function,
    };

    static DEBOUNCE_MS = 300;

    setup() {
        this.input = useRef("searchInput");
        this.state = useState({ value: this.props.query || "" });
        this._timer = null;
        onWillUnmount(() => this._clearTimer());
        // The parent resets `query` when the folder changes; mirror that into
        // the local input so the field is visibly cleared as well.
        onWillUpdateProps((nextProps) => {
            const next = nextProps.query || "";
            if (!next && this.state.value) {
                this._clearTimer();
                this.state.value = "";
            }
        });
    }

    _clearTimer() {
        if (this._timer) {
            clearTimeout(this._timer);
            this._timer = null;
        }
    }

    onInput(ev) {
        this.state.value = ev.target.value;
        this._clearTimer();
        this._timer = setTimeout(() => {
            this.props.onSearch(this.state.value);
        }, this.constructor.DEBOUNCE_MS);
    }

    onKeydown(ev) {
        if (ev.key === "Enter") {
            // Search immediately instead of waiting for the debounce.
            this._clearTimer();
            this.props.onSearch(this.state.value);
        } else if (ev.key === "Escape") {
            this.clear();
        }
    }

    clear() {
        this._clearTimer();
        this.state.value = "";
        this.props.onClear();
        if (this.input.el) {
            this.input.el.focus();
        }
    }

    get hasValue() {
        return Boolean(this.state.value);
    }
}
