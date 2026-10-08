import frappe
from frappe import _
from frappe.utils import cstr


def execute(filters=None):
    filters = filters or {}
    survey_form = filters.get("survey_form")

    if not survey_form:
        frappe.msgprint(_("Pilih Survey Form dulu."), indicator="orange", alert=True)
        return [], []

    questions = frappe.get_all(
        "Survey Form Question",
        filters={"parent": survey_form},
        fields=["name", "question", "question_type"],
        order_by="idx asc",
    )
    questions = [q for q in questions if q.question_type != "Section Break"]

    columns = get_columns(questions)
    data, response_names = get_data(filters, survey_form, questions)
    chart = get_chart(filters, survey_form, questions, response_names)
    report_summary = get_summary(data, questions)

    return columns, data, None, chart, report_summary


def get_columns(questions):
    columns = [
        {"fieldname": "respondent_name", "label": _("Nama"), "fieldtype": "Data", "width": 140},
        {"fieldname": "respondent_email", "label": _("Email"), "fieldtype": "Data", "width": 170},
        {"fieldname": "submitted_on", "label": _("Waktu Submit"), "fieldtype": "Datetime", "width": 160},
    ]
    for i, q in enumerate(questions):
        columns.append({
            "fieldname": f"q_{i}",
            "label": q.question[:45],
            "fieldtype": "Data",
            "width": 180,
        })
    return columns


def get_data(filters, survey_form, questions):
    conditions = ["r.survey_form = %(survey_form)s"]
    values = {"survey_form": survey_form}

    if filters.get("from_date"):
        conditions.append("r.submitted_on >= %(from_date)s")
        values["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        conditions.append("r.submitted_on <= %(to_date)s")
        values["to_date"] = f"{filters['to_date']} 23:59:59"

    responses = frappe.db.sql(f"""
        SELECT r.name, r.respondent_name, r.respondent_email, r.submitted_on
        FROM `tabSurvey Form Response` r
        WHERE {' AND '.join(conditions)}
        ORDER BY r.submitted_on DESC
    """, values, as_dict=True)

    if not responses:
        return [], []

    response_names = [r.name for r in responses]

    answers = frappe.db.sql("""
        SELECT parent, question, answer
        FROM `tabSurvey Response Answer`
        WHERE parent IN %(names)s
    """, {"names": response_names}, as_dict=True)

    answer_map = {}
    for a in answers:
        answer_map.setdefault(a.parent, {})[a.question] = a.answer

    data = []
    for r in responses:
        row = {
            "respondent_name": r.respondent_name,
            "respondent_email": r.respondent_email,
            "submitted_on": r.submitted_on,
        }
        row_answers = answer_map.get(r.name, {})
        for i, q in enumerate(questions):
            row[f"q_{i}"] = row_answers.get(q.question, "")
        data.append(row)

    return data, response_names


def get_chart(filters, survey_form, questions, response_names):
    question_label = filters.get("question")

    if question_label:
        q = next((q for q in questions if q.question == question_label), None)
        if q and q.question_type in ("Multiple Choice", "Checkboxes", "Dropdown", "Linear Scale"):
            return get_distribution_chart(q, response_names)

    return get_trend_chart(survey_form, filters)


def get_distribution_chart(q, response_names):
    if not response_names:
        return None

    rows = frappe.db.sql("""
        SELECT answer
        FROM `tabSurvey Response Answer`
        WHERE parent IN %(names)s AND question = %(question)s
    """, {"names": response_names, "question": q.question}, as_dict=True)

    counts = {}
    for r in rows:
        raw = r.answer or ""
        values = [v.strip() for v in raw.split(",")] if q.question_type == "Checkboxes" else [raw]
        for v in values:
            if not v:
                continue
            counts[v] = counts.get(v, 0) + 1

    if not counts:
        return None

    labels = list(counts.keys())
    values = [counts[l] for l in labels]

    return {
        "data": {
            "labels": labels,
            "datasets": [{"name": q.question[:40], "values": values}],
        },
        "type": "bar",
        "title": q.question,
    }


def get_trend_chart(survey_form, filters):
    conditions = ["survey_form = %(survey_form)s"]
    values = {"survey_form": survey_form}
    if filters.get("from_date"):
        conditions.append("submitted_on >= %(from_date)s")
        values["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        conditions.append("submitted_on <= %(to_date)s")
        values["to_date"] = f"{filters['to_date']} 23:59:59"

    rows = frappe.db.sql(f"""
        SELECT DATE(submitted_on) as d, COUNT(*) as c
        FROM `tabSurvey Form Response`
        WHERE {' AND '.join(conditions)}
        GROUP BY DATE(submitted_on)
        ORDER BY d ASC
    """, values, as_dict=True)

    if not rows:
        return None

    return {
        "data": {
            "labels": [cstr(r.d) for r in rows],
            "datasets": [{"name": _("Jumlah Response"), "values": [r.c for r in rows]}],
        },
        "type": "line",
        "title": _("Jumlah Response per Hari"),
    }


def get_summary(data, questions):
    return [
        {"label": _("Total Response"), "value": len(data), "indicator": "blue"},
        {"label": _("Total Pertanyaan"), "value": len(questions), "indicator": "green"},
    ]
