from odoo import fields, models


class CalendarEvent(models.Model):
    """Kalenderpost skapad ur en e-postinbjudan.

    Fälten behövs för att kunna känna igen en inbjudan vi redan lagt in:
    skickar organisatören en uppdatering (samma UID, högre SEQUENCE) ska
    posten uppdateras, inte dubbleras. Utan UID:t hade varje uppdatering
    blivit ett nytt möte i kalendern.
    """
    _inherit = 'calendar.event'

    vrtl_ical_uid = fields.Char(
        string='iCalendar UID',
        index=True,
        copy=False,
        help='UID från inbjudan. Används för att matcha uppdateringar och '
             'avbokningar mot rätt möte.',
    )
    vrtl_partstat = fields.Selection(
        selection=[
            ('NEEDS-ACTION', 'Ej svarat'),
            ('ACCEPTED', 'Accepterat'),
            ('DECLINED', 'Avböjt'),
            ('TENTATIVE', 'Preliminärt'),
        ],
        string='Deltagarstatus',
        copy=False,
        help='Vad vi svarat organisatören.',
    )
