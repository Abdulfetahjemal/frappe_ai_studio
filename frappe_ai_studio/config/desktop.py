# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from frappe import _


def get_data():
    return [
        {
            "module_name": "Frappe AI Studio",
            "color": "#5e64ff",
            "icon": "octicon octicon-copilot",
            "type": "module",
            "label": _("AI Studio"),
        }
    ]
