# -*- coding: utf-8 -*-
##############################################################################
#
#    Copyright (C) 2015- Vertel AB (<http://www.vertel.se>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################


from openerp import models, fields, api, _
import openerp.tools

import logging
_logger = logging.getLogger(__name__)


class res_partner(models.Model):
    _inherit = 'res.partner'

#    passwd_server = openerp.tools.config.get('passwd_server',False)
#    _logger.warning('Passwd_server %s' % passwd_server)
    service_ids = fields.Many2many('res.partner.service','res_partner_service_rel','partner_id','service_id',string="Service")
    
    
class res_partner_service(models.Model):
    _name = "res.partner.service"
    _description = "RES Partner Service"
    
    partner_id = fields.Many2one('res.partner')
    service_id = fields.Many2one('service.service')
    apache_site = fields.Text()
    bind_record = fields.Text()
    odoo_database = fields.Char()
    odoo_nbrusers = fields.Integer()
    state      = fields.Selection([('draft','Draft'),('sent','Sent'),('cancel','Cancelled'),], string='Status', index=True, readonly=False, default='draft',
                    track_visibility='onchange', copy=False,
                    help=" * The 'Draft' status is used when the password is editable.\n"
                         " * The 'Sent' status is used when the password has been sent to the user.\n"
                         " * The'Cancelled'status is used when the password has been cancelled.\n")    
#    type = fields.Selection(compu


class service(models.Model):
    _name = "service.service"
    _description = "Service"
    
    name = fields.Char()
    server_ids = fields.One2many(comodel_name='service.server',inverse_name="service_id")
    command_status = fields.Text()
    command_enable = fields.Text()
    command_disable = fields.Text()
    state = fields.Selection([('disable','Disabled'),('enable','Enabled'),('error','Error')])
    apache_site_template = fields.Text()
    bind_record_template = fields.Text()
    type = fields.Selection([('mail','Mail'),('drupal','Drupal'),('odoo','Odoo')])
    partner_ids = fields.Many2many('res.partner.service','res_partner_service_rel','partner_id','service_id',string="Partners")

class service_server(models.Model):
    _name = "service.server"
    _description = "Service Server"
    
    name = fields.Char()
    hostname = fields.Char()
    command_status = fields.Text()
    command_start = fields.Text()
    command_stop = fields.Text()
    service_id = fields.Many2one('service.service')
    state = fields.Selection([('stop','Stopped'),('start','Started'),('error','Error')])


    

    
    
