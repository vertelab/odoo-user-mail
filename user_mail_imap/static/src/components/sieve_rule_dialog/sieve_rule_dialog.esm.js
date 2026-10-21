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
        message: Object,
        close: Function,
    };

    setup() {
        this.notification = useService("notification");
        this.state = useState({
            name: "",
            conditionKind: "sender",
            conditionText: this.props.message.from_email || "",
            action: "move_to_folder",
            folder: "",
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
        const s = this.props.message.subject || "";
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

    /**
     * Servern kan bara matcha på avsändare och ämne. Väljer användaren
     * server-verkställighet med ett annat villkor tvingar vi tillbaka till
     * avsändare i stället för att låta servern avvisa — men bara som
     * vägledning; modellens constrains är den som gäller.
     */
    onEnforcementChange(value) {
        this.state.enforcement = value;
        if (value === "server" && !["sender", "subject"].includes(this.state.conditionKind)) {
            this.state.conditionKind = "sender";
        }
        if (value === "server" && !this.isServerAction) {
            this.state.action = "move_to_folder";
        }
    }

    async onConfirm() {
        if (!this.state.conditionText.trim()) {
            this.state.error = "Ange vad regeln ska matcha.";
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
                name: this.state.name.trim() || this.defaultName(),
                condition_kind: this.state.conditionKind,
                condition_text: this.state.conditionText.trim(),
                action: this.state.action,
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

    defaultName() {
        const base =
            this.state.conditionKind === "sender"
                ? this.props.message.from_email || "Avsändare"
                : this.subjectPreview || "Ämne";
        return base.slice(0, 60);
    }
}
