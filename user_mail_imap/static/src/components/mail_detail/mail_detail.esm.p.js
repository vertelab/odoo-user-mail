/** @odoo-module **/
import { Component, onWillUpdateProps, useState } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";
import { useService } from "@web/core/utils/hooks";
import {
    FLAG_OPTIONS, flagLabel,
} from "../../js/mail_flags.esm.js";

export class MailDetail extends Component {
    static template = "user_mail_imap.MailDetail";

    setup() {
        this.notification = useService("notification");
        this.state = useState({
            invitation: null,
            responding: false,
        });
        // Inbjudan hör till meddelandet — byts meddelandet ska den läsas
        // om, annars visar vyn föregående mails inbjudan.
        onWillUpdateProps((nextProps) => {
            const prev = this.props.message;
            const next = nextProps.message;
            if ((prev && prev.uid) !== (next && next.uid)) {
                this.state.invitation = null;
                if (next && next.uid) {
                    this.loadInvitation(nextProps);
                }
            }
        });
        if (this.props.message && this.props.message.uid) {
            this.loadInvitation();
        }
    }
    /**
     * Läs kalenderinbjudan när ett meddelande väljs.
     *
     * Görs som ett eget anrop i stället för att lägga inbjudningsdata i
     * varje meddelande: de allra flesta mail har ingen inbjudan, och att
     * parsa iCalendar för varje rad i listan vore slöseri.
     */
    async loadInvitation(props = null) {
        const p = props || this.props;
        const msg = p.message;
        if (!msg || !msg.uid) {
            this.state.invitation = null;
            return;
        }
        try {
            const res = await rpc("/imap/invitation", {
                folder: p.folder || "",
                uid: msg.uid,
            });
            const inv = res.invitation;
            if (!inv) {
                this.state.invitation = null;
                return;
            }
            this.state.invitation = {
                ...inv,
                startLabel: this._formatDate(inv.start),
                partstatLabel: this._partstatLabel(inv.partstat),
            };
        } catch (e) {
            // En trasig inbjudan ska inte hindra läsning av mailet.
            this.state.invitation = null;
        }
    }

    _formatDate(iso) {
        if (!iso) {
            return "";
        }
        try {
            const d = new Date(iso);
            return d.toLocaleString("sv-SE", {
                weekday: "short", day: "numeric", month: "short",
                hour: "2-digit", minute: "2-digit",
            });
        } catch (e) {
            return iso;
        }
    }

    _partstatLabel(partstat) {
        return {
            ACCEPTED: "accepterat",
            DECLINED: "avböjt",
            TENTATIVE: "preliminärt svar",
            "NEEDS-ACTION": "ej svarat",
        }[partstat] || "";
    }

    /**
     * Svara på inbjudan.
     *
     * Servern lägger in mötet i kalendern och skickar svaret till
     * organisatören. Vi laddar om inbjudningsstatusen efteråt så knapparna
     * visar det faktiska läget i stället för det vi hoppas på.
     */
    async respondInvitation(response) {
        this.state.responding = true;
        try {
            await rpc("/imap/invitation/respond", {
                folder: this.props.folder || "",
                uid: this.props.message.uid,
                response,
            });
            this.notification.add(
                { accept: "Mötet är inlagt i kalendern.",
                  tentative: "Svarat preliminärt.",
                  decline: "Inbjudan avböjd." }[response],
                { type: "success" }
            );
            await this.loadInvitation();
        } catch (e) {
            this.notification.add(
                e.message || "Kunde inte svara på inbjudan.",
                { type: "danger" }
            );
        } finally {
            this.state.responding = false;
        }
    }

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

    /** Samma sex etiketter som listans filter (js/mail_flags.esm.js). */
    get flagOptions() {
        return FLAG_OPTIONS;
    }

    flagLabel(value) {
        return flagLabel(value);
    }

    /** De etiketter som är satta på det här mailet. */
    get activeFlags() {
        const flags = (this.props.message && this.props.message.flags) || [];
        return FLAG_OPTIONS
            .filter((o) => flags.includes(o.value))
            .map((o) => o.value);
    }

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
