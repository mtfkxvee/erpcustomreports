import frappe

# ---------------------------------------------------------------------------
# Klasifikasi Member / Reseller berdasarkan frekuensi belanja (default 6 bulan)
#
# Sumber: Loyalty Point Entry (program MEMBER), non walk-in, purchase_amount > 0.
# Enrolled = Customer dgn loyalty_program MEMBER. Aktif = enrolled yg punya min.
# 1 transaksi di periode; Dormant = enrolled tanpa transaksi di periode.
#
# URL:
#   /api/method/custom_reports.member_api.get_member_classification_summary?start_date=&end_date=&months=6
#   /api/method/custom_reports.member_api.get_member_classification_list?list_type=aktif|dormant|reseller
#       &start_date=&end_date=&months=6&klasifikasi=&segmen=&search=&page=1&page_size=100   (page_size=0 -> semua)
# ---------------------------------------------------------------------------

_MEMBER_PROGRAM = "MEMBER"
_WALK_IN_CUSTOMERS = ["WALK IN CUST"]
_RESELLER_GROUP = "Reseller"

# (label, min jumlah transaksi) - urut dari yg tertinggi
_KLASIFIKASI = [
    ("RUTIN TINGGI", 10),
    ("RUTIN", 5),
    ("AKTIF", 3),
    ("SESEKALI", 2),
    ("SATU KALI", 1),
]
_KLASIFIKASI_RANGE = {
    "RUTIN TINGGI": "≥10 transaksi",
    "RUTIN": "5–9 transaksi",
    "AKTIF": "3–4 transaksi",
    "SESEKALI": "2 transaksi",
    "SATU KALI": "1 transaksi",
}
_DORMANT_LABEL = "DORMANT (0 transaksi)"
_RESELLER_DORMANT_LABEL = "RESELLER DORMANT"


def _klasifikasi(n_trx):
    for label, min_trx in _KLASIFIKASI:
        if n_trx >= min_trx:
            return label
    return _DORMANT_LABEL


def _member_period(start_date=None, end_date=None, months=6):
    end = frappe.utils.getdate(end_date) if end_date else frappe.utils.getdate(frappe.utils.today())
    if start_date:
        start = frappe.utils.getdate(start_date)
    else:
        start = frappe.utils.add_months(end, -int(months or 6))
    return start, end


def _segmen(customer_group):
    return "RESELLER" if customer_group == _RESELLER_GROUP else "MEMBER"


def _active_rows(start, end):
    walk_ph = ", ".join(["%s"] * len(_WALK_IN_CUSTOMERS))
    rows = frappe.db.sql(f"""
        SELECT c.name AS customer_id, c.customer_name, c.customer_group, c.loyalty_program_tier,
               agg.n_trx, agg.amt, agg.pts, agg.d0, agg.d1
        FROM (
            SELECT lpe.customer, COUNT(*) AS n_trx, SUM(lpe.purchase_amount) AS amt,
                   SUM(lpe.loyalty_points) AS pts,
                   MIN(lpe.posting_date) AS d0, MAX(lpe.posting_date) AS d1
            FROM `tabLoyalty Point Entry` lpe
            WHERE lpe.loyalty_program = %s
              AND lpe.posting_date BETWEEN %s AND %s
              AND lpe.purchase_amount > 0
              AND lpe.customer NOT IN ({walk_ph})
            GROUP BY lpe.customer
        ) agg
        JOIN `tabCustomer` c ON c.name = agg.customer
        WHERE c.loyalty_program = %s
    """, [_MEMBER_PROGRAM, start, end] + _WALK_IN_CUSTOMERS + [_MEMBER_PROGRAM], as_dict=True)

    out = []
    for r in rows:
        n_trx = int(r.n_trx or 0)
        amt = float(r.amt or 0)
        out.append({
            "customer_id": r.customer_id,
            "nama_customer": r.customer_name or r.customer_id,
            "grup": r.customer_group or "-",
            "tier": r.loyalty_program_tier or "-",
            "segmen": _segmen(r.customer_group),
            "klasifikasi": _klasifikasi(n_trx),
            "jumlah_transaksi": n_trx,
            "total_purchase_rp": round(amt, 2),
            "avg_per_transaksi_rp": round(amt / n_trx) if n_trx else 0,
            "poin_loyalty": int(r.pts or 0),
            "tgl_pertama": str(r.d0) if r.d0 else None,
            "tgl_terakhir": str(r.d1) if r.d1 else None,
        })
    out.sort(key=lambda x: (-x["jumlah_transaksi"], -x["total_purchase_rp"], x["nama_customer"]))
    return out


def _dormant_rows(start, end):
    walk_ph = ", ".join(["%s"] * len(_WALK_IN_CUSTOMERS))
    rows = frappe.db.sql(f"""
        SELECT c.name AS customer_id, c.customer_name, c.customer_group, c.loyalty_program_tier
        FROM `tabCustomer` c
        LEFT JOIN (
            SELECT DISTINCT lpe.customer
            FROM `tabLoyalty Point Entry` lpe
            WHERE lpe.loyalty_program = %s
              AND lpe.posting_date BETWEEN %s AND %s
              AND lpe.purchase_amount > 0
              AND lpe.customer NOT IN ({walk_ph})
        ) act ON act.customer = c.name
        WHERE c.loyalty_program = %s
          AND act.customer IS NULL
    """, [_MEMBER_PROGRAM, start, end] + _WALK_IN_CUSTOMERS + [_MEMBER_PROGRAM], as_dict=True)

    out = []
    for r in rows:
        is_reseller = r.customer_group == _RESELLER_GROUP
        out.append({
            "customer_id": r.customer_id,
            "nama_customer": r.customer_name or r.customer_id,
            "grup": r.customer_group or "-",
            "tier": r.loyalty_program_tier or "-",
            "segmen": _segmen(r.customer_group),
            "klasifikasi": _RESELLER_DORMANT_LABEL if is_reseller else _DORMANT_LABEL,
        })
    out.sort(key=lambda x: (x["nama_customer"], x["customer_id"]))
    return out


@frappe.whitelist()
def get_member_classification_summary(start_date=None, end_date=None, months=6):
    start, end = _member_period(start_date, end_date, months)
    active = _active_rows(start, end)
    dormant = _dormant_rows(start, end)

    n_active, n_dormant = len(active), len(dormant)
    n_enrolled = n_active + n_dormant
    total_trx = sum(r["jumlah_transaksi"] for r in active)
    total_amt = sum(r["total_purchase_rp"] for r in active)
    trx_counts = sorted(r["jumlah_transaksi"] for r in active)
    if trx_counts:
        mid = len(trx_counts) // 2
        median = trx_counts[mid] if len(trx_counts) % 2 else (trx_counts[mid - 1] + trx_counts[mid]) / 2
    else:
        median = 0

    segmentasi = []
    for label, _min in _KLASIFIKASI:
        sub = [r for r in active if r["klasifikasi"] == label]
        amt = sum(r["total_purchase_rp"] for r in sub)
        segmentasi.append({
            "klasifikasi": label,
            "keterangan": _KLASIFIKASI_RANGE[label],
            "jumlah": len(sub),
            "pct_dari_aktif": round(len(sub) / n_active * 100, 2) if n_active else 0,
            "pct_dari_enrolled": round(len(sub) / n_enrolled * 100, 2) if n_enrolled else 0,
            "total_purchase_rp": round(amt, 2),
            "avg_purchase_rp": round(amt / len(sub)) if sub else 0,
        })
    segmentasi.append({
        "klasifikasi": _DORMANT_LABEL,
        "keterangan": "0 transaksi",
        "jumlah": n_dormant,
        "pct_dari_aktif": 0,
        "pct_dari_enrolled": round(n_dormant / n_enrolled * 100, 2) if n_enrolled else 0,
        "total_purchase_rp": 0,
        "avg_purchase_rp": 0,
    })

    return {
        "start_date": str(start), "end_date": str(end),
        "loyalty_program": _MEMBER_PROGRAM,
        "generated_at": str(frappe.utils.now_datetime()),
        "total_enrolled": n_enrolled,
        "aktif": n_active,
        "dormant": n_dormant,
        "reseller": {
            "aktif": sum(1 for r in active if r["segmen"] == "RESELLER"),
            "dormant": sum(1 for r in dormant if r["segmen"] == "RESELLER"),
        },
        "total_transaksi": total_trx,
        "total_purchase_rp": round(total_amt, 2),
        "avg_purchase_per_customer_rp": round(total_amt / n_active) if n_active else 0,
        "median_transaksi_per_customer": median,
        "segmentasi": segmentasi,
        "note": (
            "Sumber: Loyalty Point Entry program MEMBER, exclude WALK IN CUST, hanya entry dgn purchase_amount > 0 "
            "(entry redeem/adjustment/opening tidak dihitung sbg transaksi). Klasifikasi: RUTIN TINGGI >=10, "
            "RUTIN 5-9, AKTIF 3-4, SESEKALI 2, SATU KALI 1 transaksi. Dormant = customer MEMBER tanpa transaksi di periode."
        ),
    }


@frappe.whitelist()
def get_member_classification_list(list_type="aktif", start_date=None, end_date=None, months=6,
                                   klasifikasi=None, segmen=None, search=None, page=1, page_size=100):
    list_type = (list_type or "aktif").lower()
    if list_type not in ("aktif", "dormant", "reseller"):
        frappe.throw("list_type harus salah satu dari: aktif, dormant, reseller")
    start, end = _member_period(start_date, end_date, months)

    if list_type == "aktif":
        rows = _active_rows(start, end)
    elif list_type == "dormant":
        rows = _dormant_rows(start, end)
    else:
        rows = []
        for r in _active_rows(start, end):
            if r["segmen"] == "RESELLER":
                rows.append(dict(r, status="AKTIF"))
        for r in _dormant_rows(start, end):
            if r["segmen"] == "RESELLER":
                rows.append(dict(r, status="DORMANT", klasifikasi="DORMANT", jumlah_transaksi=0,
                                 total_purchase_rp=None, avg_per_transaksi_rp=None, poin_loyalty=None,
                                 tgl_pertama=None, tgl_terakhir=None))

    if klasifikasi:
        k = klasifikasi.strip().upper()
        rows = [r for r in rows if r["klasifikasi"] == k]
    if segmen:
        s = segmen.strip().upper()
        rows = [r for r in rows if r["segmen"] == s]
    if search:
        q = search.strip().lower()
        rows = [r for r in rows if q in r["customer_id"].lower() or q in (r["nama_customer"] or "").lower()]

    total = len(rows)
    page = max(int(page or 1), 1)
    page_size = int(page_size or 0)
    if page_size > 0:
        offset = (page - 1) * page_size
        rows = rows[offset:offset + page_size]
    else:
        offset = 0
    for i, r in enumerate(rows):
        r["no"] = offset + i + 1

    return {
        "list_type": list_type,
        "start_date": str(start), "end_date": str(end),
        "total": total,
        "page": page if page_size > 0 else 1,
        "page_size": page_size,
        "total_pages": (-(-total // page_size) if page_size > 0 else 1),
        "rows": rows,
    }
