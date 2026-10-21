/** @odoo-module **/
import { Component } from "@odoo/owl";

export class MailDetail extends Component {
    static template = "user_mail_imap.MailDetail";
    static props = {
        message: { type: [Object, { value: null }], optional: true },
        loading: Boolean,
        openComposer: Function,
        openRuleDialog: Function,
        // Verktygsraden (Thunderbird-ordning). Arkivera/Skräppost/Ta bort
        // flyttar meddelandet till en mapp; stjärnan sätter \Flagged.
        onArchive: Function,
        onJunk: Function,
        onDelete: Function,
        onToggleFlag: Function,
    };

    /**
     * Iframen ska bli så hög som innehållet kräver.
     *
     * Utan detta blir den 150 px (webbläsarens default) och långa mail
     * klipps av. `contentDocument` går att läsa trots sandbox eftersom
     * allow-same-origin är satt — med enbart allow-scripts hade detta
     * kastat SecurityError.
     */
    onIframeLoad(ev) {
        const doc = ev.target.contentDocument;
        if (doc && doc.body) {
            ev.target.style.height = doc.body.scrollHeight + 'px';
        }
    }
}
