import frappe


def run():
    osi_name = "OSI-2026-0636"
    old_name = "ACC-SINV-2026-356502-1"

    si = frappe.get_doc("Sales Invoice", old_name)
    if si.docstatus == 1:
        si.cancel()
        frappe.db.commit()

    new = frappe.copy_doc(si)
    new.amended_from = si.name
    new.docstatus = 0

    # Bersihkan margin yang nyangkut dari pricing rule lama - field ini
    # tetap dipakai Frappe saat recalculate total walau ignore_pricing_rule=1,
    # menyebabkan rate item 97635 ke-mark up +1600 lagi.
    fixed = 0
    for item in new.items:
        item.margin_type = ""
        item.margin_rate_or_amount = 0
        item.rate_with_margin = 0
        item.base_rate_with_margin = 0
        if item.item_code == "38304" and fixed < 3:
            item.rate = 24849
            fixed += 1

    new.ignore_pricing_rule = 1
    new.flags.ignore_permissions = True
    new.insert(ignore_permissions=True)
    new.reload()

    if new.payments:
        new.payments[0].amount = new.grand_total
        new.payments[0].base_amount = new.grand_total
    new.paid_amount = new.grand_total
    new.flags.ignore_permissions = True
    new.save(ignore_permissions=True)
    new.submit()

    frappe.db.sql(
        "UPDATE `tabSales Invoice` SET ignore_pricing_rule = 1, custom_outlet = %s WHERE name = %s",
        (new.custom_outlet, new.name),
    )
    frappe.db.sql(
        "DELETE FROM `tabSales Invoice Item` WHERE parent = %s AND is_free_item = 1",
        new.name,
    )

    created = frappe.db.get_value("Online Sales Import", osi_name, "created_invoices") or ""
    created_list = [x.strip() for x in created.strip().split("\n") if x.strip()]
    created_list = [new.name if x == old_name else x for x in created_list]
    frappe.db.set_value("Online Sales Import", osi_name, "created_invoices", "\n".join(created_list))

    log = frappe.db.get_value("Online Sales Import", osi_name, "import_log") or ""
    if old_name in log:
        log = log.replace(old_name, "{} (fixed margin, was {})".format(new.name, old_name))
        frappe.db.set_value("Online Sales Import", osi_name, "import_log", log)

    frappe.db.commit()

    print("CANCELLED:", si.name)
    print("NEW INVOICE:", new.name)
    print("NEW GRAND TOTAL:", new.grand_total)
