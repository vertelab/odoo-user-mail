/** @odoo-module **/
import { Component } from "@odoo/owl";

export class MailDetail extends Component {
    static template = "user_mail_imap.MailDetail";
    static props = {
        // `optional: true` only allows `undefined`. The parent passes the
        // store's `selectedMessage`, which is `null` when nothing is selected,
        // so the type must accept `null` explicitly.
        message: { type: [Object, { value: null }], optional: true },
        loading: { type: Boolean, optional: true },
        openComposer: Function,
        openRuleDialog: Function,
    };

    /**
     * Intercept link clicks inside the rendered message.
     *
     * The backend already adds target="_blank" to links, but this covers
     * links that appear through other means and guarantees a consistent
     * behaviour. Opening in a new window keeps the mail client in place:
     * navigating the iframe to an Odoo URL would be refused by the browser
     * because Odoo sends X-Frame-Options: DENY on its webclient.
     */
    onIframeLoad(ev) {
        let doc;
        try {
            doc = ev.target.contentDocument;
        } catch (e) {
            // Sandboxed cross-origin document — the target attribute from the
            // backend is the fallback, so there is nothing to do here.
            return;
        }
        if (!doc) {
            return;
        }
        doc.addEventListener("click", (e) => {
            const link = e.target.closest("a[href]");
            if (!link) {
                return;
            }
            const href = link.getAttribute("href");
            if (!href || href.startsWith("#")) {
                return;
            }
            e.preventDefault();
            window.open(href, "_blank", "noopener,noreferrer");
        });
    }
}
