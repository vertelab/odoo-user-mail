/** @odoo-module **/
import { Component, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { rpc } from "@web/core/network/rpc";
import { useService } from "@web/core/utils/hooks";

/**
 * Skapa en mailregel direkt från ett meddelande.
 *
 * Poängen är att användaren ska slippa skriva av avsändaren för hand — det
 * är där felstavningarna blir till regler som aldrig matchar. Fälten
 * förifylls från det valda meddelandet och användaren bekräftar.
 *
 * Dialogen skapar en `user_mail_ai.rule` med enforcement='server' förvalt:
 * det är den vanligaste avsikten ("sluta visa det här i inkorgen"), och
 * servern kan utföra den. Väljer användaren en åtgärd som Sieve inte klarar
 * avvisar serverns validering — den kontrollen ligger i modellen, inte här,
 * så regeln kan inte kringgås via ett annat gränssnitt.
 */
export class SieveRuleDialog extends Component {
    static template = "user_mail_imap.SieveRuleDialog";
    static components = { Dialog };
    static props = {
        // `close` injiceras av dialogService, inte av anroparen.
        close: { type: Function, optional: true },
        message: { type: [Object, { value: null }], optional: true },
    };

    setup() {
        this.notification = useService("notification");
        this.state = useState({
            name: "",
            conditionKind: "sender",
            conditionText: (this.props.message && this.props.message.from_email) || "",
            conditionHeader: "",
            action: "move_to_folder",
            flagKind: "flagged",
            folder: "",
            newFolder: "",
            creatingFolder: false,
            enforcement: "server",
            folders: [],
            saving: false,
            error: null,
        });
        this.loadFolders();
    }

    /**
     * Mapplistan kommer från IMAP, inte från Odoo — det är brevlådans egna
     * mappar som gäller, och en mapp som inte finns på servern gör att
     * fileinto avvisas. Därför får användaren välja ur listan i stället för
     * att skriva ett namn.
     */
    async loadFolders() {
        try {
            const folders = await rpc("/imap/folders");
            this.state.folders = (folders || [])
                .filter((f) => !f.noselect && !f.name.startsWith("dovecot"))
                .map((f) => f.name);
        } catch (e) {
            // Ingen mapplista betyder inte att regeln är omöjlig — bara att
            // användaren får skriva namnet själv.
            this.state.folders = [];
        }
    }

    get subjectPreview() {
        const s = (this.props.message && this.props.message.subject) || "";
        return s.length > 60 ? s.slice(0, 60) + "…" : s;
    }

    /** Sieve-åtgärder vs. åtgärder som kräver Odoo. */
    get isServerAction() {
        return ["move_to_folder", "flag", "ignore", "block"].includes(
            this.state.action
        );
    }

    get needsFolder() {
        return this.state.action === "move_to_folder";
    }

    get needsFlag() {
        return this.state.action === "flag";
    }

    get needsHeader() {
        return this.state.conditionKind === "header";
    }

    /**
     * Meddelandets egna headers, för väljaren.
     *
     * Att skriva headernamnet ur minnet är hur man får en regel som
     * aldrig matchar: mailet har "X-Spam-flag", användaren skriver
     * "X-Spam-Flag", och Sieve matchar skiftlägesokänsligt på namnet men
     * användaren har ingen aning om varför regeln sover.
     */
    get availableHeaders() {
        const h = this.props.message && this.props.message.headers;
        return Array.isArray(h) ? h : [];
    }

    /**
     * Header vald ur listan — fyll även i värdet.
     *
     * Värdet är det som ska matchas, och det står i headern. Att fylla i
     * det sparar avskrivning och gör regeln rätt från början.
     */
    onHeaderSelect(name) {
        this.state.conditionHeader = name || "";
        const found = this.availableHeaders.find((h) => h.name === name);
        this.state.conditionText = found ? (found.value || "") : "";
        this.syncName();
    }

    /**
     * Förslag på regelnamn, uppdaterat när villkoret ändras.
     *
     * Namnet är det användaren ser i regellistan, så det ska säga vad
     * regeln gör. Förslag byggs av villkorstyp + värde:
     *   Avsändare breakit.se      → "Från breakit.se"
     *   Ämne "JULREA"             → "Ämne JULREA"
     *   Header X-Spam-Flag = YES  → "X-Spam-Flag: YES"
     *
     * Fältet är redigerbart — förslaget skrivs bara in om användaren inte
     * redan skrivit ett eget namn. Annars skulle en ändrad avsändare
     * skriva över namnet man just valt.
     */
    suggestedName() {
        const text = (this.state.conditionText || "").trim();
        const header = (this.state.conditionHeader || "").trim();
        let base;
        switch (this.state.conditionKind) {
            case "sender":
                base = text ? `Från ${text}` : "Från avsändare";
                break;
            case "subject":
                base = text ? `Ämne ${text}` : "Ämne";
                break;
            case "header":
                base = header
                    ? `${header}${text ? `: ${text}` : ""}`
                    : "Header";
                break;
            default:
                base = "Regel";
        }
        return base.slice(0, 60);
    }

    /**
     * Villkorstypen byts — fyll i textrutan med det som är känt.
     *
     * Utan detta står textrutan kvar med föregående värde: väljer man
     * "Ämne" efter att ha haft "Avsändare" ligger avsändaren kvar som
     * ämne, och regeln matchar aldrig. Det är precis den sortens tysta fel
     * dialogen finns för att undvika.
     */
    onConditionKindChange(kind) {
        this.state.conditionKind = kind;
        const msg = this.props.message || {};
        if (kind === "sender") {
            this.state.conditionText = msg.from_email || "";
        } else if (kind === "subject") {
            this.state.conditionText = msg.subject || "";
        } else if (kind === "header") {
            // Header-värdet är okänt — vi har inte meddelandets råa headers.
            // Töm fältet hellre än att lämna kvar ett värde som ser rätt ut
            // men matchar fel header.
            this.state.conditionText = "";
        }
        this.syncName();
    }

    /** Skriv in förslaget om användaren inte satt ett eget namn. */
    syncName() {
        if (!this.state.name || this.state.name === this._lastSuggestion) {
            this.state.name = this.suggestedName();
            this._lastSuggestion = this.state.name;
        }
    }

    onConditionTextChange(value) {
        this.state.conditionText = value;
        this.syncName();
    }

    onHeaderChange(value) {
        this.state.conditionHeader = value;
        this.syncName();
    }

    /**
     * Servern kan matcha på avsändare, ämne och valfri header. Väljer
     * användaren server-verkställighet med ett annat villkor tvingar vi
     * tillbaka till avsändare i stället för att låta servern avvisa — men
     * bara som vägledning; modellens constrains är den som gäller.
     */
    onEnforcementChange(value) {
        this.state.enforcement = value;
        if (value === "server" && !["sender", "subject", "header"].includes(this.state.conditionKind)) {
            this.onConditionKindChange("sender");
        }
        if (value === "server" && !this.isServerAction) {
            this.state.action = "move_to_folder";
        }
    }

    /**
     * Skapa en ny mapp på servern.
     *
     * Sieve:s `fileinto :create` skapar mappen vid leverans, men först när
     * ett mail matchar — användaren ser den inte i mappträdet förrän dess.
     * Att skapa den direkt ger omedelbar bekräftelse på att namnet är
     * giltigt, och mappen syns på en gång.
     */
    async onCreateFolder() {
        const name = (this.state.newFolder || "").trim();
        if (!name) {
            return;
        }
        this.state.creatingFolder = true;
        this.state.error = null;
        try {
            await rpc("/imap/folder/create", { name });
            await this.loadFolders();
            this.state.folder = name;
            this.state.newFolder = "";
            this.notification.add(`Mappen "${name}" skapades.`, { type: "success" });
        } catch (e) {
            this.state.error = e.message || String(e);
        } finally {
            this.state.creatingFolder = false;
        }
    }

    async onConfirm() {
        if (!this.state.conditionText.trim()) {
            this.state.error = "Ange vad regeln ska matcha.";
            return;
        }
        if (this.needsHeader && !this.state.conditionHeader.trim()) {
            this.state.error = "Ange vilken header som ska matchas.";
            return;
        }
        if (this.needsFolder && !this.state.folder.trim()) {
            this.state.error = "Välj en mapp att flytta till.";
            return;
        }
        this.state.saving = true;
        this.state.error = null;
        try {
            await rpc("/imap/rule/create", {
                name: this.state.name.trim() || this.suggestedName(),
                condition_kind: this.state.conditionKind,
                condition_text: this.state.conditionText.trim(),
                condition_header: this.state.conditionHeader.trim(),
                action: this.state.action,
                flag_kind: this.state.flagKind,
                folder: this.state.folder.trim(),
                enforcement: this.state.enforcement,
            });
            this.notification.add("Regeln är sparad.", { type: "success" });
            this.props.close();
        } catch (e) {
            // Visa felet i dialogen i stället för att stänga — användaren
            // ska kunna rätta och försöka igen utan att börja om.
            this.state.error = e.message || String(e);
        } finally {
            this.state.saving = false;
        }
    }
}
