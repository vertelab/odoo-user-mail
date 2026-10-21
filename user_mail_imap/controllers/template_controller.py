from odoo import http
from odoo.http import request


class ImapTemplateController(http.Controller):

    @http.route('/imap/templates', type='json', auth='user')
    def templates(self):
        """List mail.templates available for the user.

        Samma urval som Odoos chatter: användarens egna mallar OCH de som
        saknar ägare. Att bara matcha ``user_id = env.user.id`` gav noll
        träffar — Odoos standardmallar har ingen ``user_id``, och då såg
        mallväljaren tom ut trots 26 mallar i databasen.

        ``model_id`` styr om mallen kan renderas: en mall bunden till
        sale.order kräver en order som kontext. De visas ändå, men
        anroparen får ``model_id`` med så den kan avgöra.
        """
        Template = request.env['mail.template'].sudo()
        records = Template.search_read(
            ['|', ('user_id', '=', request.env.user.id), ('user_id', '=', False)],
            ['id', 'name', 'subject', 'body_html', 'model_id'],
            order='name',
        )
        return {'templates': records}

    @http.route('/imap/template/render', type='json', auth='user')
    def template_render(self, template_id):
        """Render a mail.template and return subject + body."""
        template = request.env['mail.template'].sudo().browse(template_id)
        if not template.exists():
            return {'error': 'Template not found'}
        rendered = template._render_template(
            template.body_html,
            template.model_id.model,
            request.env.user.id,
        )
        return {
            'subject': template.subject or '',
            'body_html': rendered.get(template.lang or '') or rendered.get('') or '',
        }

    @http.route('/imap/partners', type='json', auth='user')
    def partners(self, query=''):
        """Search res.partner by email or name for recipient autocomplete."""
        Partner = request.env['res.partner'].sudo()
        domain = [('email', '!=', False)]
        if query:
            domain += ['|', ('email', 'ilike', query), ('name', 'ilike', query)]
        records = Partner.search_read(domain, ['id', 'name', 'email'], limit=20)
        return {'partners': records}
