import base64

import frappe
import requests

BASE_URL = "https://api.repliz.com"
LOOKBACK_DAYS = 14
MAX_PAGES_PER_ACCOUNT = 5


def _get_auth_header():
    access_key = frappe.conf.get("repliz_access_key")
    secret_key = frappe.conf.get("repliz_secret_key")
    if not access_key or not secret_key:
        frappe.throw("Repliz API credentials belum di-setup di site_config.json")
    token = base64.b64encode(f"{access_key}:{secret_key}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _get_accounts():
    accounts = []
    page = 1
    while True:
        resp = requests.get(
            f"{BASE_URL}/public/account",
            params={"page": page, "limit": 50},
            headers=_get_auth_header(),
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        accounts.extend(data.get("docs", []))
        if not data.get("hasNextPage"):
            break
        page += 1
    return accounts


def _get_content(account_id, cutoff):
    items = []
    next_token = None
    for _ in range(MAX_PAGES_PER_ACCOUNT):
        params = {"accountId": account_id}
        if next_token:
            params["nextToken"] = next_token
        resp = requests.get(f"{BASE_URL}/public/content", params=params, headers=_get_auth_header(), timeout=30)
        if resp.status_code != 200:
            # keep whatever was already collected from earlier pages instead of losing it
            break
        data = resp.json()
        page_items = data.get("docs", [])
        items.extend(page_items)
        next_token = data.get("nextToken")

        oldest_on_page = None
        for it in page_items:
            d = frappe.utils.getdate(it.get("createdAt")) if it.get("createdAt") else None
            if d and (oldest_on_page is None or d < oldest_on_page):
                oldest_on_page = d
        if oldest_on_page and oldest_on_page < cutoff:
            break

        if not next_token:
            break
    return items


def _get_statistic(account_id, content_id):
    resp = requests.get(
        f"{BASE_URL}/public/content/{content_id}/statistic",
        params={"accountId": account_id},
        headers=_get_auth_header(),
        timeout=30,
    )
    if resp.status_code != 200:
        return {}
    return resp.json()


def sync_social_content():
    try:
        accounts = _get_accounts()
    except Exception:
        frappe.log_error(title="Repliz sync: gagal ambil daftar akun")
        return {"error": "failed to fetch accounts"}

    cutoff = frappe.utils.getdate(frappe.utils.add_days(frappe.utils.nowdate(), -LOOKBACK_DAYS))
    synced = 0
    errors = 0

    for account in accounts:
        account_id = account.get("id") or account.get("_id")
        platform = account.get("type")
        account_name = account.get("username") or account.get("name")

        try:
            contents = _get_content(account_id, cutoff)
        except Exception:
            frappe.log_error(title=f"Repliz sync: gagal ambil content untuk {account_name}")
            errors += 1
            continue

        for item in contents:
            content_id = item.get("id")
            created_at = item.get("createdAt")
            posting_date = frappe.utils.getdate(created_at) if created_at else None
            if posting_date and posting_date < frappe.utils.getdate(cutoff):
                continue

            try:
                stats = _get_statistic(account_id, content_id)
            except Exception:
                stats = {}

            values = {
                "platform": platform,
                "account_name": account_name,
                "posting_date": posting_date,
                "content_type": item.get("type"),
                "caption": item.get("description"),
                "url": item.get("url"),
                "likes": stats.get("like", 0),
                "comments": stats.get("comment", 0),
                "shares": stats.get("share", 0),
                "saved": stats.get("saved", stats.get("favourite", 0)),
                "views": stats.get("views", 0),
                "reach": stats.get("reach", 0),
                "interactions": stats.get("interaction", 0),
                "repliz_content_id": content_id,
                "repliz_account_id": account_id,
            }

            try:
                existing = frappe.db.get_value(
                    "Marketing Social Content",
                    {"repliz_content_id": content_id, "repliz_account_id": account_id},
                    "name",
                )
                if existing:
                    doc = frappe.get_doc("Marketing Social Content", existing)
                    doc.update(values)
                    doc.save(ignore_permissions=True)
                else:
                    doc = frappe.get_doc({"doctype": "Marketing Social Content", **values})
                    doc.insert(ignore_permissions=True)
                synced += 1
            except Exception:
                frappe.log_error(title=f"Repliz sync: gagal simpan content {content_id}")
                errors += 1

    frappe.db.commit()
    return {"accounts": len(accounts), "synced": synced, "errors": errors}
