/** @odoo-module **/
import { Component, useState, onWillStart, useRef } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

export class Composer extends Component {
    static template = "user_mail_imap.Composer";
    static props = {
        type: String,
        // Opened with `openComposer('new', null)`, so this prop receives
        // `null` — `optional: true` alone only tolerates `undefined`.
        message: { type: [Object, { value: null }], optional: true },
        onSend: Function,
        onClose: Function,
    };

    setup() {
        this.store = useService("user_mail_imap.store");
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.dialog = useService("dialog");

        this.toInputRef = useRef("toInput");
        this.ccInputRef = useRef("ccInput");

        this.data = useState({
            to: [],
            cc: [],
            subject: '',
            body: '',
            // Bilagor: {id, name, content_type, size, sizeLabel, data}
            // där data är base64 utan prefix. Läses in i webbläsaren och
            // följer med i anropet — inget lagras på servern.
            attachments: [],
        });
        this.toInputValue = useState({ val: '' });
        this.ccInputValue = useState({ val: '' });
        this.templates = useState([]);
        this.partnerSuggestions = useState([]);
        this.ccSuggestions = useState([]);
        this._partnerTimer = null;
        this._ccTimer = null;

        if (this.props.message && this.props.type === 'reply') {
            const fromAddr = this._extractEmail(this.props.message.from_);
            if (fromAddr) this.data.to = [fromAddr];
            this.data.subject = this.props.message.subject.startsWith('Re:')
                ? this.props.message.subject
                : 'Re: ' + this.props.message.subject;
            this.data.body = '\n\n--- Originalmeddelande ---\n'
                + 'Från: ' + (this.props.message.from_ || '')
                + '\nDatum: ' + (this.props.message.date || '')
                + '\n\n' + (this.props.message.body_html || '');
        } else if (this.props.message && this.props.type === 'forward') {
            this.data.subject = this.props.message.subject.startsWith('Fwd:')
                ? this.props.message.subject
                : 'Fwd: ' + this.props.message.subject;
            this.data.body = '\n\n--- Vidarebefordrat meddelande ---\n'
                + 'Från: ' + (this.props.message.from_ || '')
                + '\nDatum: ' + (this.props.message.date || '')
                + '\n\n' + (this.props.message.body_html || '');
        }

        onWillStart(async () => {
            try {
                const templates = await this.store.fetchTemplates();
                this.templates = templates;
            } catch (e) { /* optional */ }
        });
    }

    _extractEmail(raw) {
        if (!raw) return null;
        const match = raw.match(/<([^>]+)>/) || raw.match(/([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})/);
        return match ? match[1] : raw.trim();
    }

    /* ---- Tag input helpers ---- */

    addTag(field, value) {
        const addr = value.trim().replace(/[,;]$/, '').trim();
        if (!addr || !addr.includes('@')) return;
        if (!this.data[field].includes(addr)) {
            this.data[field] = [...this.data[field], addr];
        }
        if (field === 'to') this.toInputValue.val = '';
        else this.ccInputValue.val = '';
        if (field === 'to') this.partnerSuggestions = [];
        else this.ccSuggestions = [];
    }

    removeTag(field, index) {
        this.data[field] = this.data[field].filter((_, i) => i !== index);
    }

    onTagKeydown(field, ev) {
        const currentVal = field === 'to' ? this.toInputValue.val : this.ccInputValue.val;
        if ((ev.key === 'Enter' || ev.key === ',') && currentVal.trim()) {
            ev.preventDefault();
            this.addTag(field, currentVal);
        } else if (ev.key === 'Backspace' && !currentVal && this.data[field].length) {
            this.data[field] = this.data[field].slice(0, -1);
        } else if (ev.key === 'Escape') {
            if (field === 'to') this.partnerSuggestions = [];
            else this.ccSuggestions = [];
        }
    }

    onTagInput(field, value) {
        if (field === 'to') this.toInputValue.val = value;
        else this.ccInputValue.val = value;
        this._debouncePartnerSearch(value, field);
    }

    _debouncePartnerSearch(query, field) {
        const timerField = field === 'to' ? '_partnerTimer' : '_ccTimer';
        const suggestionsField = field === 'to' ? 'partnerSuggestions' : 'ccSuggestions';
        clearTimeout(this[timerField]);
        if (query.length < 2) {
            this[suggestionsField] = [];
            return;
        }
        this[timerField] = setTimeout(async () => {
            try {
                const partners = await this.store.searchPartners(query);
                // Filter out already added
                const added = field === 'to' ? this.data.to : this.data.cc;
                this[suggestionsField] = partners.filter(p => !added.includes(p.email));
            } catch (e) { /* ignore */ }
        }, 250);
    }

    selectPartner(field, partner) {
        this.addTag(field, partner.email);
    }

    /* ---- Templates ---- */

    async onLoadTemplate(tmpl) {
        try {
            const rendered = await this.store.renderTemplate(tmpl.id);
            if (rendered.error) {
                this.notification.add(rendered.error, { type: 'danger' });
                return;
            }
            this.data.subject = rendered.subject || this.data.subject;
            if (rendered.body_html) {
                const div = document.createElement('div');
                div.innerHTML = rendered.body_html;
                this.data.body = div.textContent || div.innerText || '';
            }
        } catch (e) {
            this.notification.add('Kunde inte ladda mallen', { type: 'danger' });
        }
    }

    async onSaveTemplate() {
        if (!this.data.subject && !this.data.body) {
            this.notification.add('Fyll i ämne eller text först', { type: 'warning' });
            return;
        }
        try {
            await this.orm.create('mail.template', [{
                name: this.data.subject || 'IMAP-mall',
                subject: this.data.subject,
                body_html: '<p>' + this.data.body.replace(/\n/g, '</p><p>') + '</p>',
                model_id: false,
            }]);
            this.notification.add('Mallen sparades', { type: 'success' });
            const templates = await this.store.fetchTemplates();
            this.templates = templates;
        } catch (e) {
            this.notification.add('Kunde inte spara mallen', { type: 'danger' });
        }
    }

    async onOpenAI() {
        try {
            const mod = await odoo.loader.modules.get('@html_editor/main/chatgpt/chatgpt_prompt_dialog');
            if (mod?.ChatGPTPromptDialog) {
                this.dialog.add(mod.ChatGPTPromptDialog, {
                    insert: (content) => {
                        const div = document.createElement('div');
                        div.appendChild(content);
                        this.data.body += '\n' + (div.textContent || div.innerText || '');
                    },
                    sanitize: (fragment) => DOMPurify.sanitize(fragment, {
                        IN_PLACE: true,
                        ADD_TAGS: ["#document-fragment"],
                        ADD_ATTR: ["contenteditable"],
                    }),
                });
            }
        } catch (e) {
            this.notification.add('AI-funktionen kräver html_editor-modulen', { type: 'info' });
        }
    }

    /* ---- Send ---- */

    /**
     * Läs in valda filer som base64.
     *
     * FileReader krävs — filen finns bara i webbläsaren. Vi läser hela
     * filen i minnet: ett mail med bilagor skickas ändå i ett svep över
     * SMTP, så någon streamingvinst finns inte att hämta här.
     *
     * Gränsen är 25 MB per fil. SMTP-servern avvisar större, och att
     * upptäcka det först vid sändning gör att användaren förlorar
     * meddelandet den skrivit.
     */
    onAttach(ev) {
        const files = Array.from(ev.target.files || []);
        ev.target.value = '';
        for (const file of files) {
            if (file.size > 25 * 1024 * 1024) {
                this.notification.add(
                    `"${file.name}" är större än 25 MB och kan inte bifogas.`,
                    { type: 'danger' }
                );
                continue;
            }
            const reader = new FileReader();
            reader.onload = () => {
                // result är en data-URL: "data:<typ>;base64,<data>".
                const result = String(reader.result || '');
                const comma = result.indexOf(',');
                this.data.attachments.push({
                    id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
                    name: file.name,
                    content_type: file.type || 'application/octet-stream',
                    size: file.size,
                    sizeLabel: this._formatSize(file.size),
                    data: comma >= 0 ? result.slice(comma + 1) : result,
                });
            };
            reader.onerror = () => {
                this.notification.add(
                    `Kunde inte läsa "${file.name}".`,
                    { type: 'danger' }
                );
            };
            reader.readAsDataURL(file);
        }
    }

    removeAttachment(id) {
        this.data.attachments = this.data.attachments.filter((a) => a.id !== id);
    }

    _formatSize(bytes) {
        if (bytes < 1024) {
            return `${bytes} B`;
        }
        if (bytes < 1024 * 1024) {
            return `${Math.round(bytes / 1024)} kB`;
        }
        return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    }

    send() {
        if (!this.data.to.length) {
            this.notification.add('Minst en mottagare krävs', { type: 'warning' });
            return;
        }
        this.props.onSend({
            to: this.data.to.join(', '),
            cc: this.data.cc.join(', '),
            subject: this.data.subject,
            body: this.data.body,
            attachments: this.data.attachments.map((a) => ({
                filename: a.name,
                content_type: a.content_type,
                data: a.data,
            })),
        });
    }
}
