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

    # this controller will control url: /image/image_id/magic/recipe_id
    @http.route(['/website/publisher_info',
                 ], type='http', auth="public", website=True)
    def publisher_info(self, **post):
        return render-something
    # this controller will control url: /image/image_url/magic/recipe_id
    @http.route(['/website/module.info'], type='http', auth="public", website=True)
    def module_info(self, url=None, recipe=None, recipe_ref=None, **post):
        if recipe_ref:
            recipe = request.env.ref(recipe_ref) # 'imagemagick.my_recipe'        
        return recipe.send_file(http, url=url)


#~ class image_recipe(models.Model):
    #~ _name = "image.recipe"
