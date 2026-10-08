# Laporan Follow Up Task: Overdue / Deadline Hari Ini / Deadline Dekat (default 3
# hari ke depan), diurutkan priority (High dulu) lalu tanggal deadline.
# URL: /api/method/custom_reports.task_api.get_task_followup?due_soon_days=3

import frappe

_PRIORITY_RANK = {"Urgent": 0, "High": 1, "Medium": 2, "Low": 3}
_FOLLOWUP_ASSIGNEE = "risarosalina08@gmail.com"


def _parse_assign(assign_json):
    if not assign_json:
        return []
    try:
        return frappe.parse_json(assign_json)
    except Exception:
        return []


@frappe.whitelist()
def get_task_followup(due_soon_days=3):
    today = frappe.utils.getdate(frappe.utils.today())
    due_soon_days = int(due_soon_days)
    window_end = frappe.utils.add_days(today, due_soon_days)

    rows = frappe.db.sql("""
        SELECT t.name, t.subject, t.project, p.project_name, t.status, t.priority,
               t.exp_end_date, t.description, t._assign
        FROM `tabTask` t
        LEFT JOIN `tabProject` p ON p.name = t.project
        WHERE t.status NOT IN ('Completed', 'Cancelled')
          AND t.exp_end_date IS NOT NULL
          AND t.exp_end_date <= %s
          AND t._assign LIKE %s
        ORDER BY t.exp_end_date ASC
    """, (window_end, f"%{_FOLLOWUP_ASSIGNEE}%"), as_dict=True)

    overdue, due_today, due_soon = [], [], []
    for r in rows:
        exp_end = r["exp_end_date"]
        days_diff = (exp_end - today).days
        assigned = _parse_assign(r["_assign"])
        row = {
            "task_id": r["name"],
            "subject": r["subject"],
            "project": r["project_name"] or r["project"],
            "status": r["status"],
            "priority": r["priority"],
            "exp_end_date": str(exp_end),
            "note": r["description"],
            "assigned_to": assigned,
        }
        if days_diff < 0:
            row["days_overdue"] = -days_diff
            overdue.append(row)
        elif days_diff == 0:
            due_today.append(row)
        else:
            row["days_remaining"] = days_diff
            due_soon.append(row)

    for group in (overdue, due_today, due_soon):
        group.sort(key=lambda r: (_PRIORITY_RANK.get(r["priority"], 9), r["exp_end_date"]))

    return {
        "as_of_date": str(today),
        "due_soon_days": due_soon_days,
        "overdue": overdue,
        "due_today": due_today,
        "due_soon": due_soon,
        "total_overdue": len(overdue),
        "total_due_today": len(due_today),
        "total_due_soon": len(due_soon),
    }


# --- Laporan Task yang DI-UPDATE hari itu, pakai field bawaan `modified`
# (otomatis ke-update Frappe tiap ada perubahan apapun ke task - status,
# catatan, priority, dll - tanpa perlu setting tambahan). Kasih tau kondisi
# task SEKARANG, bukan field apa berubah dari apa ke apa (utk itu perlu
# doctype 'Version' yg track_changes-nya sedang mati di Task doctype ini).
# URL: /api/method/custom_reports.task_api.get_task_updates_today?date=YYYY-MM-DD

@frappe.whitelist()
def get_task_updates_today(date=None):
    target_date = frappe.utils.getdate(date) if date else frappe.utils.getdate(frappe.utils.today())
    next_date = frappe.utils.add_days(target_date, 1)

    rows = frappe.db.sql("""
        SELECT t.name, t.subject, t.project, p.project_name, t.status, t.priority,
               t.exp_end_date, t.description, t.modified
        FROM `tabTask` t
        LEFT JOIN `tabProject` p ON p.name = t.project
        WHERE t.modified >= %s AND t.modified < %s
          AND t._assign LIKE %s
        ORDER BY t.modified DESC
    """, (target_date, next_date, f"%{_FOLLOWUP_ASSIGNEE}%"), as_dict=True)

    tasks = []
    for r in rows:
        tasks.append({
            "task_id": r["name"],
            "subject": r["subject"],
            "project": r["project_name"] or r["project"],
            "status": r["status"],
            "priority": r["priority"],
            "exp_end_date": str(r["exp_end_date"]) if r["exp_end_date"] else None,
            "note": r["description"],
            "last_updated": str(r["modified"]),
        })

    return {
        "date": str(target_date),
        "total_tasks_updated": len(tasks),
        "tasks": tasks,
    }
