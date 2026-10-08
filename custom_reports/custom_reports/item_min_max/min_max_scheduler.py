import frappe


def check_overstock():
    """
    Cek item yang actual_qty di Bin melebihi max_qty di Item Min Max.
    Kirim System Notification ke owner masing-masing record.
    """
    overstock_items = frappe.db.sql(
        """
        SELECT
            m.name,
            m.item_code,
            m.item_name,
            m.warehouse,
            m.max_qty,
            m.owner,
            b.actual_qty
        FROM `tabItem Min Max` m
        JOIN `tabBin` b
            ON b.item_code = m.item_code
            AND b.warehouse = m.warehouse
        WHERE m.is_active = 1
          AND b.actual_qty > m.max_qty
        ORDER BY m.owner, m.warehouse, m.item_code
        """,
        as_dict=True,
    )

    if not overstock_items:
        return

    # Kelompokkan per owner
    grouped = {}
    for row in overstock_items:
        grouped.setdefault(row.owner, []).append(row)

    for owner, items in grouped.items():
        # Pastikan user ada
        if not frappe.db.exists("User", owner):
            continue

        # Bangun isi pesan
        rows_html = "".join(
            f"""<tr>
                <td>{r.item_code}</td>
                <td>{r.item_name or ""}</td>
                <td>{r.warehouse}</td>
                <td style="text-align:right">{r.max_qty:,.2f}</td>
                <td style="text-align:right;color:red"><b>{r.actual_qty:,.2f}</b></td>
                <td style="text-align:right;color:red"><b>{r.actual_qty - r.max_qty:,.2f}</b></td>
            </tr>"""
            for r in items
        )

        message = f"""
        <p>Berikut item yang stok aktualnya melebihi <b>Max Qty</b> pada Item Min Max:</p>
        <table border="1" cellpadding="5" cellspacing="0" style="border-collapse:collapse;width:100%">
            <thead style="background:#f5f5f5">
                <tr>
                    <th>Item Code</th>
                    <th>Item Name</th>
                    <th>Warehouse</th>
                    <th>Max Qty</th>
                    <th>Actual Qty</th>
                    <th>Selisih</th>
                </tr>
            </thead>
            <tbody>{rows_html}</tbody>
        </table>
        <p>Total item overstock: <b>{len(items)}</b></p>
        """

        subject = f"[Overstock Warning] {len(items)} item melebihi Max Qty"

        try:
            frappe.get_doc({
                "doctype": "Notification Log",
                "subject": subject,
                "email_content": message,
                "type": "Alert",
                "document_type": "Item Min Max",
                "document_name": items[0].name,
                "from_user": "Administrator",
                "for_user": owner,
            }).insert(ignore_permissions=True)
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                f"Overstock Notification Failed: {owner}"
            )

    frappe.db.commit()
