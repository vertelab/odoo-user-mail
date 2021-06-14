# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution, third party addon
#    Copyright (C) 2004-2015 Vertel AB (<http://vertel.se>).
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

from datetime import datetime
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo import http
from odoo.http import request
import werkzeug

_logger = logging.getLogger(__name__)


class website_publisher_info(http.Controller):

    @http.route(['/website/publisher_info'], type='http', auth="public", website=True)
    def publisher_info(self, **post):
        me = request.env['res.users'].browse(request.context['uid'])
        values = {'me': me}
        return request.website.render("website_publisher_info.publisher_info_template", values)

    @http.route(['/website/publisher_info/<model("ir.module.module"):module>'], type='http', auth="public", website=True)
    def publisher_info_module(self, module=None, **post):
        return request.website.render("website_publisher_info.publisher_info_module", {'module': module})

