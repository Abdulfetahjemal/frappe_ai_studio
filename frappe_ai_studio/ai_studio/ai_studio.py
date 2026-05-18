# -*- coding: utf-8 -*-
"""Page controller for AI Studio."""

from __future__ import unicode_literals

import frappe
from frappe import _


def get_context(context):
    context.no_cache = 1
    context.title = _("AI Studio")
    context.show_sidebar = False
