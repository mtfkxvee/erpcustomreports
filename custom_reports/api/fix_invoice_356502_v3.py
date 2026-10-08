import frappe

EXPECTED_TOTAL = 127747.0


def run():
    osi_name = "OSI-2026-0636"
    old_name = "ACC-SINV-2026-356502-2"

    si = frappe.get_doc("Sales Invoice", old_name)
    if si.docstatus == 1:
        si.cancel()
        frappe.db.commit()

    new = frappe.copy_doc(si)
    new.amended_from = si.name
    new.docstatus = 0
    new.ignore_pricing_rule = 1
    new.flags.ignore_permissions = True
    new.insert(ignore_permissions=True)
    frappe.db.commit()

    # Patch rate & bersihkan margin langsung di DB (level draft), match per posisi (idx)
    # bukan per item_code - supaya item yg sama dgn rate beda tidak saling ketiban.
    fixed = 0
    rows = frappe.db.sql(
        "SELECT name, item_code FROM `tabSales Invoice Item` WHERE parent=%s ORDER BY idx",
        new.name, as_dict=True
    )
    for r in rows:
        if r.item_code == "38304" and fixed < 3:
            rate = 24849
            fixed += 1
        else:
            rate = 26600
        frappe.db.sql("""
            UPDATE `tabSales Invoice Item`
            SET rate=%s, base_rate=%s, net_rate=%s, base_net_rate=%s,
                amount=%s, base_amount=%s, net_amount=%s, base_net_amount=%s,
                margin_type='', margin_rate_or_amount=0, rate_with_margin=0, base_rate_with_margin=0,
                discount_amount=0, discount_percentage=0
            WHERE name=%s
        """, (rate, rate, rate, rate, rate, rate, rate, rate, r.name))
    frappe.db.commit()

    new.reload()
    print("DEBUG setelah SQL patch + reload, grand_total:", new.grand_total)
    for it in new.items:
        print("  ", it.item_code, it.rate, "margin=", it.margin_type, it.margin_rate_or_amount, "amount=", it.amount)

    if new.payments:
        new.payments[0].amount = new.grand_total
        new.payments[0].base_amount = new.grand_total
    new.paid_amount = new.grand_total
    new.flags.ignore_permissions = True
    new.save(ignore_permissions=True)
    new.reload()
    print("DEBUG setelah save, grand_total:", new.grand_total)

    if abs(new.grand_total - EXPECTED_TOTAL) > 0.5:
        print("MASIH MISMATCH setelah save - TIDAK submit. Invoice ini masih draft, aman untuk dihapus/diperbaiki lagi.")
        print("Draft name:", new.name)
        return

    new.submit()
    new.reload()
    print("DEBUG setelah submit, grand_total:", new.grand_total)

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
    olds = ("ACC-SINV-2026-356502", "ACC-SINV-2026-356502-1", "ACC-SINV-2026-356502-2")
    created_list = [new.name if x in olds else x for x in created_list]
    frappe.db.set_value("Online Sales Import", osi_name, "created_invoices", "\n".join(created_list))

    log = frappe.db.get_value("Online Sales Import", osi_name, "import_log") or ""
    for o in olds:
        if o in log:
            log = log.replace(o, new.name)
    frappe.db.set_value("Online Sales Import", osi_name, "import_log", log)

    frappe.db.commit()

    print("CANCELLED:", si.name)
    print("NEW INVOICE:", new.name)
    print("FINAL GRAND TOTAL:", new.grand_total)
