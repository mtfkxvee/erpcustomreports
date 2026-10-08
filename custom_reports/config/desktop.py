from frappe import _

def get_data():
    return [
        {
            "module_name": "Custom Reports",
            "color": "#7575ff",
            "icon": "octicon octicon-file-text",
            "type": "module",
            "label": _("Custom Reports"),
            "items": [
                {
                    "type": "doctype",
                    "name": "Item Conversion",
                    "label": _("Item Conversion"),
                    "description": _("Konversi item XSHA ke item online"),
                },
                {
                    "type": "doctype",
                    "name": "Item Conversion Template",
                    "label": _("Item Conversion Template"),
                    "description": _("Template mapping item XSHA ke online"),
                },
            ]
        }
    ]
