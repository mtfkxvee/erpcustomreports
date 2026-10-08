import frappe

EXPECTED_TOTAL = 127747.0


def run():
    osi_name = "OSI-2026-0636"
    old_name = "ACC-SINV-2026-356502-3"

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

    # Save DULU tanpa sentuh payment supaya grand_total kehitung ulang dgn benar,
    # baru reload untuk ambil grand_total yang sudah final.
    new.reload()
    new.flags.ignore_permissions = True
    new.save(ignore_permissions=True)
    new.reload()
    print("DEBUG grand_total setelah save pertama (sebelum fix payment):", new.grand_total)

    if abs(new.grand_total - EXPECTED_TOTAL) > 0.5:
        print("MASIH MISMATCH - TIDAK lanjut. Draft name:", new.name)
        return

    # Sekarang set payment sesuai grand_total yang sudah benar & final.
    if new.payments:
        new.payments[0].amount = new.grand_total
        new.payments[0].base_amount = new.grand_total
    new.paid_amount = new.grand_total
    new.change_amount = 0
    new.base_change_amount = 0
    new.flags.ignore_permissions = True
    new.save(ignore_permissions=True)
    new.reload()
    print("DEBUG grand_total setelah save kedua (payment fixed):", new.grand_total, "paid_amount:", new.paid_amount, "outstanding:", new.outstanding_amount)

    if abs(new.grand_total - EXPECTED_TOTAL) > 0.5 or abs(new.paid_amount - new.grand_total) > 0.5:
        print("MASIH MISMATCH setelah fix payment - TIDAK submit. Draft name:", new.name)
        return

    new.submit()
    new.reload()
    print("DEBUG setelah submit, grand_total:", new.grand_total, "outstanding:", new.outstanding_amount)

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
    olds = ("ACC-SINV-2026-356502", "ACC-SINV-2026-356502-1", "ACC-SINV-2026-356502-2", "ACC-SINV-2026-356502-3")
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
