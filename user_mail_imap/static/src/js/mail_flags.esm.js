/** @odoo-module **/

/**
 * Flaggtyperna — EN definition för hela klienten.
 *
 * Listans filter och meddelandevyns etikettmeny visar samma sex etiketter.
 * Låg listan tidigare med sin egen kopia här och detaljvyn med en annan
 * hade de kunnat glida isär tyst: en etikett som går att sätta men inte
 * filtrera på (eller tvärtom). Därför exporteras listan härifrån och båda
 * komponenterna importerar den.
 *
 * `flagged`/`important` är standardflaggor (RFC 3501) som syns i alla
 * klienter. `todo`/`personal`/`work` är IMAP-nyckelord — samma märkning
 * Thunderbird använder. `spam` sätts som Junk-nyckelord.
 *
 * `seen` finns med flit INTE här: oläst är en egen axel (IMAP UNSEEN), inte
 * en etikett man sätter på ett mail. Att lägga den i listan skulle både
 * erbjuda "oläst" som etikett och ge två vägar till samma serverfält som
 * markera-som-läst.
 */
export const FLAG_OPTIONS = [
    { value: 'flagged', label: 'Stjärnmärkta', icon: 'fa-star text-warning' },
    { value: 'important', label: 'Viktiga', icon: 'fa-check-circle text-success' },
    { value: 'spam', label: 'Skräppost', icon: 'fa-ban text-danger' },
    { value: 'todo', label: 'Att göra', icon: 'fa-tasks text-primary' },
    { value: 'personal', label: 'Privat', icon: 'fa-user text-info' },
    { value: 'work', label: 'Arbete', icon: 'fa-briefcase text-secondary' },
];

/** Ikon för en flaggtyp; stjärna som fallback. */
export function flagIcon(value) {
    const opt = FLAG_OPTIONS.find((o) => o.value === value);
    return opt ? opt.icon : 'fa-star-o';
}

/** Etikett för en flaggtyp; "Alla mail" när inget filter är satt. */
export function flagLabel(value) {
    const opt = FLAG_OPTIONS.find((o) => o.value === value);
    return opt ? opt.label : 'Alla mail';
}
