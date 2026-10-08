import frappe
from frappe.utils import get_url, md_to_html


def _resolve_image(path):
    if not path:
        return None
    if path.startswith("http"):
        return path
    return get_url(path)


def _resolve_content(post):
    if post.content_type == "Markdown":
        return md_to_html(post.content_md or "")
    if post.content_type == "HTML":
        return post.content_html or ""
    return post.content or ""


def _resolve_category(blog_category):
    if not blog_category:
        return None
    return frappe.db.get_value("Blog Category", blog_category, "title") or blog_category


def _resolve_blogger(blogger):
    if not blogger:
        return None
    return frappe.db.get_value("Blogger", blogger, "full_name") or blogger


def _serialize_list(post):
    return {
        "name": post.name,
        "title": post.title,
        "blog_intro": post.blog_intro,
        "published_on": str(post.published_on) if post.published_on else None,
        "blog_category": _resolve_category(post.blog_category),
        "blogger": _resolve_blogger(post.blogger),
        "meta_image": _resolve_image(post.meta_image),
        "read_time": post.read_time,
    }


@frappe.whitelist(allow_guest=True)
def get_blog_posts(limit=20, offset=0, category=None):
    filters = {"published": 1}
    if category:
        cat_name = frappe.db.get_value("Blog Category", {"title": category}, "name") or category
        filters["blog_category"] = cat_name

    posts = frappe.get_all(
        "Blog Post",
        filters=filters,
        fields=[
            "name", "title", "blog_intro", "published_on",
            "blog_category", "blogger", "meta_image", "read_time",
        ],
        order_by="published_on desc",
        limit_page_length=limit,
        limit_start=offset,
    )
    return [_serialize_list(frappe._dict(p)) for p in posts]


@frappe.whitelist(allow_guest=True)
def get_blog_post(name):
    post = frappe.get_doc("Blog Post", name)
    if not post.published:
        frappe.throw("Post not found", frappe.DoesNotExistError)

    data = _serialize_list(post)
    data["content"] = _resolve_content(post)
    return data


@frappe.whitelist(allow_guest=True)
def get_related_blog_posts(name, limit=3):
    post = frappe.get_doc("Blog Post", name)
    related = frappe.get_all(
        "Blog Post",
        filters={
            "published": 1,
            "blog_category": post.blog_category,
            "name": ["!=", name],
        },
        fields=[
            "name", "title", "blog_intro", "published_on",
            "blog_category", "blogger", "meta_image", "read_time",
        ],
        order_by="published_on desc",
        limit_page_length=limit,
    )
    return [_serialize_list(frappe._dict(p)) for p in related]
