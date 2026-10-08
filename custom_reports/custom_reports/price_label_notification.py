import frappe
from frappe.utils import now_datetime, add_days, get_datetime
from frappe import _


def send_price_label_notifications():
    """Dijalankan setiap jam oleh scheduler."""
    now = now_datetime()
    current_hour   = now.hour
    current_minute = now.minute

    # Ambil semua notifikasi yang aktif
    notifications = frappe.get_all(
        "Price Label Notification",
        filters={"enabled": 1},
        fields=["name", "send_time", "last_sent"]
    )

    for notif in notifications:
        if not notif.send_time:
            continue

        # Parse jam kirim
        send_time = str(notif.send_time)
        try:
            parts    = send_time.split(":")
            send_h   = int(parts[0])
            send_m   = int(parts[1]) if len(parts) > 1 else 0
        except:
            continue

        # Cek apakah sudah waktunya (dalam window 5 menit)
        if current_hour != send_h:
            continue
        if abs(current_minute - send_m) > 5:
            continue

        # Cek apakah sudah dikirim setelah jam kirim hari ini
        if notif.last_sent:
            last_sent_dt = get_datetime(notif.last_sent)
            # Buat datetime jam kirim hari ini
            from datetime import datetime
            send_today = datetime(now.year, now.month, now.day, send_h, send_m, 0)
            # Skip jika last_sent sudah setelah jam kirim hari ini
            if last_sent_dt >= send_today:
                continue

        # Kirim notifikasi
        try:
            send_notification(notif.name)
            frappe.db.set_value("Price Label Notification", notif.name, "last_sent", now)
            frappe.db.commit()
        except Exception as e:
            frappe.log_error("Price Label Notification Error: {}".format(str(e)))


def send_notification(notification_name):
    doc = frappe.get_doc("Price Label Notification", notification_name)

    if not doc.price_lists:
        return
    if not doc.recipients:
        return

    price_list_names = [r.price_list for r in doc.price_lists]
    # Ambil sejak last_sent atau 24 jam lalu jika belum pernah kirim
    if doc.last_sent:
        since = str(frappe.utils.get_datetime(doc.last_sent).date())
    else:
        since = add_days(frappe.utils.today(), -1)

    # Cari item price yang berubah atau baru dalam 24 jam
    fmt = ", ".join(["%s"] * len(price_list_names))
    # Build IN clause langsung sebagai string untuk hindari conflict format
    in_str = "({})".format(", ".join(["'{}'".format(p.replace("'","''")) for p in price_list_names]))
    changed_items = frappe.db.sql("""
        SELECT
            ip.item_code,
            i.item_name,
            ip.price_list,
            ip.price_list_rate,
            ip.currency,
            ip.modified,
            ip.modified_by,
            CASE WHEN DATE(ip.creation) = DATE(ip.modified) THEN 'Baru' ELSE 'Update Harga' END AS status
        FROM `tabItem Price` ip
        JOIN `tabItem` i ON i.name = ip.item_code
        WHERE ip.price_list IN {in_str}
        AND DATE(ip.modified) >= %(since)s
        ORDER BY ip.modified DESC
    """.format(in_str=in_str), {"since": since}, as_dict=True)

    if not changed_items:
        return

    # Build email HTML
    site_url = frappe.utils.get_url()
    email_html = build_email_html(changed_items, site_url)

    # Kirim ke semua penerima
    recipient_emails = [r.email for r in doc.recipients if r.email]
    if not recipient_emails:
        return

    frappe.sendmail(
        recipients=recipient_emails,
        subject="[X-SHA] Update Harga Item - {}".format(frappe.utils.today()),
        message=email_html,
        header=["Update Harga Item", "orange"],
    )


def build_email_html(items, site_url, outlet=""):
    # Group by price_list
    groups = {}
    for item in items:
        pl = item["price_list"]
        if pl not in groups:
            groups[pl] = []
        groups[pl].append(item)

    html = """
    <div style="font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto;">
        <h2 style="color: #70357D; border-bottom: 2px solid #70357D; padding-bottom: 8px;">
            Update Harga Item
        </h2>
        <p style="color: #666;">Berikut adalah item yang mengalami perubahan harga atau item baru dalam 24 jam terakhir.</p>
    """

    for price_list, pl_items in groups.items():
        # Buat dokumen Price Label baru dengan item sudah terisi
        try:
            pl_doc = frappe.new_doc("PRICE LABEL")
            pl_doc.pricelist = price_list
            pl_doc.tanggal   = frappe.utils.today()
            # Ambil outlet dari warehouse default jika tidak diset
            wh_outlet = outlet or frappe.db.get_single_value("Stock Settings", "default_warehouse") or ""
            pl_doc.outlet = wh_outlet
            for item_data in pl_items:
                pl_doc.append("qty", {
                    "item_code": item_data["item_code"],
                    "item_name": item_data.get("item_name", ""),
                    "price":     float(item_data.get("price_list_rate") or 0),
                })
            pl_doc.flags.ignore_mandatory = True
            pl_doc.insert(ignore_permissions=True)
            frappe.db.commit()
            price_label_link = "{}/app/price-label/{}".format(site_url, pl_doc.name)
        except Exception as e:
            frappe.log_error("Price Label Create Error: {}".format(str(e)))
            price_label_link = "{}/app/price-label/new-price-label-1".format(site_url)

        html += """
        <div style="margin-bottom: 30px;">
            <h3 style="color: #F5A623; margin-bottom: 10px;">
                {} 
                <a href="{}" style="font-size: 13px; background: #70357D; color: white; padding: 5px 12px; border-radius: 4px; text-decoration: none; margin-left: 10px;">
                    🏷 Buka Price Label
                </a>
            </h3>
            <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
                <thead>
                    <tr style="background: #70357D; color: white;">
                        <th style="padding: 8px; text-align: left;">Kode Item</th>
                        <th style="padding: 8px; text-align: left;">Nama Item</th>
                        <th style="padding: 8px; text-align: right;">Harga</th>
                        <th style="padding: 8px; text-align: center;">Status</th>
                        <th style="padding: 8px; text-align: center;">Diubah Oleh</th>
                        <th style="padding: 8px; text-align: center;">Waktu</th>
                    </tr>
                </thead>
                <tbody>
        """.format(price_list, price_label_link)

        for i, item in enumerate(pl_items):
            bg = "#fff" if i % 2 == 0 else "#f9f9f9"
            status_color = "#2e7d32" if item["status"] == "Baru" else "#f57f17"
            html += """
                    <tr style="background: {};">
                        <td style="padding: 7px 8px; font-family: monospace;">{}</td>
                        <td style="padding: 7px 8px;">{}</td>
                        <td style="padding: 7px 8px; text-align: right; font-weight: bold;">Rp {:,.0f}</td>
                        <td style="padding: 7px 8px; text-align: center;">
                            <span style="background: {}; color: white; padding: 2px 8px; border-radius: 10px; font-size: 11px;">{}</span>
                        </td>
                        <td style="padding: 7px 8px; text-align: center; color: #666; font-size: 11px;">{}</td>
                        <td style="padding: 7px 8px; text-align: center; color: #666; font-size: 11px;">{}</td>
                    </tr>
            """.format(
                bg,
                item["item_code"],
                item["item_name"],
                float(item["price_list_rate"]),
                status_color,
                item["status"],
                item["modified_by"].split("@")[0] if "@" in str(item["modified_by"]) else item["modified_by"],
                str(item["modified"])[:16]
            )

        html += """
                </tbody>
            </table>
            <p style="font-size: 12px; color: #999; margin-top: 5px;">Total: {} item</p>
        </div>
        """.format(len(pl_items))

    html += """
        <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
        <p style="color: #999; font-size: 11px; text-align: center;">
            Email ini dikirim otomatis oleh sistem X-SHA ERP
        </p>
    </div>
    """

    return html


@frappe.whitelist()
def send_now(notification_name):
    """Kirim notifikasi sekarang tanpa menunggu scheduler."""
    try:
        send_notification(notification_name)
        frappe.db.set_value("Price Label Notification", notification_name, "last_sent", frappe.utils.now_datetime())
        frappe.db.commit()
        return {"status": "success", "message": "Email berhasil dikirim!"}
    except Exception as e:
        frappe.log_error("Price Label Send Now Error: {}".format(str(e)))
        return {"status": "error", "message": str(e)}

