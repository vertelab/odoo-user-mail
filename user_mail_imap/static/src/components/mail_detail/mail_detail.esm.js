/** @odoo-module **/
import { Component } from "@odoo/owl";

export class MailDetail extends Component {
    static template = "user_mail_imap.MailDetail";
    /**
     * Nedladdningslänk för en bilaga.
     *
     * Pekar på controllern, inte på ett RPC-anrop: webbläsaren ska få
     * filen som en fil. Mappen måste med — bilagan slås upp via UID, och
     * UID är bara unikt inom en mapp.
     */
    attachmentUrl(att, index) {
        // Mappen kommer som prop — UID är bara unikt inom en mapp, så
        // bilagan går inte att slå upp utan den.
        const folder = this.props.folder || '';
        const uid = (this.props.message && this.props.message.uid) || 0;
        return `/imap/attachment?folder=${encodeURIComponent(folder)}`
            + `&uid=${uid}&index=${index}`;
    }

    static props = {
        message: { type: [Object, { value: null }], optional: true },
        // Aktuell mapp. Behövs för att ladda ner bilagor — UID är bara
        // unikt inom en mapp.
        folder: { type: String, optional: true },
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
