import frappe

# Report yg diganti nama (2026-10-17) supaya sama dgn daftar laporan admin (Teh
# Risa) & gampang dicari di ERP. Folder report lama sudah dihapus dari app, jadi
# record Report lama di database dihapus juga supaya tdk muncul di pencarian &
# tdk error kalau dibuka.
OLD_TO_NEW = {
    "Weekly Margin": "Weekly Margin Target vs Achievement",
    "Weekly Sales Net Achievement": "Weekly Sales Achievement Net Retur dan Potongan",
    "Kontribusi Sales per Category": "Weekly Kontribusi Sales per Category",
}


def execute():
    for old in OLD_TO_NEW:
        if frappe.db.exists("Report", old):
            frappe.delete_doc("Report", old, ignore_permissions=True, force=True)
