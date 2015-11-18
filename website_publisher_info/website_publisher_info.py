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

from openerp import models, fields, api, _
from openerp.exceptions import except_orm, Warning, RedirectWarning
from openerp import http
from openerp.http import request
from openerp import SUPERUSER_ID
from datetime import datetime
from openerp.modules import get_module_resource, get_module_path
import werkzeug

import logging
_logger = logging.getLogger(__name__)

class website_publisher_info(http.Controller):

     # this controller will render publisher information
    @http.route(['/website/publisher_info'], type='http', auth="public", website=True)
    def publisher_info(self, **post):
        
        return request.website.render("website_publisher_info.publisher_info_page")
        
        
    @http.route(['/website/user_info'], type='http', auth="public", website=True)
    def user_info(self, **post):
        
        return request.website.render("website_publisher_info.user_info_page")
        
    # this controller will list all modules installed on database
    @http.route(['/website/info'], type='http', auth="public", website=True)
    def module_info(self, url=None, recipe=None, recipe_ref=None, **post):
        if recipe_ref:
            recipe = request.env.ref(recipe_ref) # 'imagemagick.my_recipe'        
        return recipe.send_file(http, url=url)

