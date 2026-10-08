import base64
import json
import re

import frappe

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

DEFAULT_SUBJECT = 'Terima kasih sudah mengisi "{survey_title}"'
DEFAULT_MESSAGE = """
    <p>Halo {name},</p>
    <p>Terima kasih sudah meluangkan waktu untuk mengisi survey <b>{survey_title}</b>.
    Jawaban kamu sudah kami terima dan tersimpan dengan baik.</p>
    <p>Salam,<br>X-SHA</p>
"""


def _get_published_survey(form_key):
    survey = frappe.db.get_value(
        "Survey Form",
        {"form_key": form_key},
        ["name", "title", "status", "collect_email", "allow_multiple_responses",
         "send_confirmation_email", "confirmation_email_subject", "confirmation_email_message"],
        as_dict=True,
    )
    if not survey:
        frappe.throw("Survey tidak ditemukan", frappe.DoesNotExistError)
    if survey.status != "Published":
        frappe.throw("Survey ini sudah tidak menerima jawaban")
    return survey


@frappe.whitelist(allow_guest=True)
def upload_survey_answer_file(form_key, filename, content_base64):
    _get_published_survey(form_key)

    if not filename or not content_base64:
        frappe.throw("File tidak valid")

    raw = content_base64.split(",")[-1]
    file_content = base64.b64decode(raw)

    file_doc = frappe.get_doc({
        "doctype": "File",
        "file_name": filename,
        "is_private": 0,
        "content": file_content,
    })
    file_doc.insert(ignore_permissions=True)
    return {"file_url": file_doc.file_url}


def _send_confirmation_email(survey, respondent_name, respondent_email):
    if not survey.collect_email or not survey.send_confirmation_email:
        return
    if not respondent_email or not EMAIL_RE.match(respondent_email):
        return

    name = respondent_name or ""
    placeholders = {"survey_title": survey.title, "name": name or "kamu"}

    subject_tpl = survey.confirmation_email_subject or DEFAULT_SUBJECT
    message_tpl = survey.confirmation_email_message or DEFAULT_MESSAGE

    try:
        subject = subject_tpl.format(**placeholders)
    except (KeyError, ValueError, IndexError):
        subject = subject_tpl

    try:
        message = message_tpl.format(**placeholders)
    except (KeyError, ValueError, IndexError):
        message = message_tpl

    try:
        frappe.sendmail(
            recipients=[respondent_email],
            subject=subject,
            message=message,
            now=True,
        )
    except Exception:
        frappe.log_error(title="Survey confirmation email failed")


@frappe.whitelist(allow_guest=True)
def submit_response(form_key, answers, respondent_name=None, respondent_email=None):
    survey = _get_published_survey(form_key)

    if isinstance(answers, str):
        answers = json.loads(answers)

    if survey.collect_email and not (respondent_name or respondent_email):
        frappe.throw("Nama/email responden wajib diisi")

    if not survey.allow_multiple_responses and respondent_email:
        already = frappe.db.exists("Survey Form Response", {
            "survey_form": survey.name,
            "respondent_email": respondent_email,
        })
        if already:
            frappe.throw("Kamu sudah pernah mengisi survey ini")

    questions = frappe.get_all(
        "Survey Form Question",
        filters={"parent": survey.name, "parenttype": "Survey Form"},
        fields=["name", "question", "question_type", "is_required"],
        ignore_permissions=True,
    )

    response = frappe.get_doc({
        "doctype": "Survey Form Response",
        "survey_form": survey.name,
        "submitted_on": frappe.utils.now_datetime(),
        "respondent_name": respondent_name,
        "respondent_email": respondent_email,
    })

    for q in questions:
        value = answers.get(q.name)

        if q.question_type == "Section Break":
            continue

        if q.is_required and not value:
            frappe.throw(f'Pertanyaan "{q.question}" wajib diisi')

        if isinstance(value, list):
            value = ", ".join(value)

        response.append("answers", {
            "question": q.question,
            "question_type": q.question_type,
            "answer": value or "",
        })

    response.insert(ignore_permissions=True)
    frappe.db.commit()

    _send_confirmation_email(survey, respondent_name, respondent_email)

    return {"success": True, "name": response.name}


def add_no_cache_headers(response, request):
	if request.path.startswith("/form/") or request.path.startswith("/api/method/custom_reports.api.survey."):
		response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
		response.headers["Pragma"] = "no-cache"
