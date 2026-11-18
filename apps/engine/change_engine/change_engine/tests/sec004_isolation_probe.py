"""SEC-004 test probe: engine-side helpers for the cross-tenant isolation suite.

Called only through `bench --site <site> execute change_engine.tests.sec004_isolation_probe.<fn>`
on a throwaway SEC-004 bench (see infra/dev/docker/isolation/). Nothing here is
whitelisted, so none of it is reachable over HTTP. Synthetic data only.
"""

from __future__ import annotations

import time

import frappe


def create_todo(marker: str) -> str:
    """Insert a ToDo whose description carries a tenant marker; return its name."""
    doc = frappe.get_doc({"doctype": "ToDo", "description": marker}).insert(ignore_permissions=True)
    return doc.name


def create_file(file_name: str, content: str, is_private: int) -> dict:
    """Store a synthetic file in the current site's file store; return url and path."""
    doc = frappe.get_doc(
        {"doctype": "File", "file_name": file_name, "is_private": int(is_private), "content": content}
    ).insert(ignore_permissions=True)
    return {"name": doc.name, "file_url": doc.file_url, "full_path": doc.get_full_path()}


def make_api_token() -> str:
    """Generate an API key and secret for Administrator on the current site."""
    from frappe.core.doctype.user.user import generate_keys

    keys = generate_keys("Administrator")
    return f"{keys['api_key']}:{keys['api_secret']}"


def cache_set(key: str, value: str) -> str:
    frappe.cache.set_value(key, value)
    return "ok"


def cache_get(key: str):
    return {"value": frappe.cache.get_value(key)}


def cache_key_bytes(key: str) -> str:
    """The raw Redis key the engine uses for `key` on the current site."""
    return frappe.cache.make_key(key).decode()


def record_job_site(token: str, **attacker_kwargs) -> None:
    """Background job body: record which site and user it actually ran under (as a ToDo)."""
    frappe.get_doc(
        {"doctype": "ToDo",
         "description": f"sec004_job_{token}|{frappe.local.site}|{frappe.session.user}|{sorted(attacker_kwargs)}"}
    ).insert(ignore_permissions=True)
    frappe.db.commit()


def enqueue_record_job_site(token: str, attacker_site: str) -> str:
    """Enqueue record_job_site, smuggling another tenant's site and user as kwargs."""
    job = frappe.enqueue(
        "change_engine.tests.sec004_isolation_probe.record_job_site",
        queue="short",
        token=token,
        site=attacker_site,
        user="Administrator",
    )
    return job.id


def enqueue_marker_job(marker: str) -> str:
    """Enqueue a no-op job whose kwargs carry a tenant marker (as RQ Job arguments)."""
    job = frappe.enqueue(
        "change_engine.tests.sec004_isolation_probe.noop_job", queue="short", payload=marker
    )
    return job.id


def noop_job(payload: str) -> str:
    return payload


def _job_record(token: str):
    rows = frappe.db.sql(
        "select description from `tabToDo` where description like %s", (f"sec004_job_{token}|%",)
    )
    return rows[0][0] if rows else None


def get_job_record(token: str):
    return {"value": _job_record(token)}


def wait_for_job_record(token: str, timeout: int = 90):
    deadline = time.time() + int(timeout)
    while time.time() < deadline:
        frappe.db.rollback()  # fresh snapshot so the worker's commit is visible
        value = _job_record(token)
        if value:
            return {"value": value}
        time.sleep(1)
    return {"value": None}


def site_paths() -> dict:
    """Real paths of this site's private files and backups directories."""
    import os

    return {
        "site_path": os.path.realpath(frappe.get_site_path()),
        "private_files": os.path.realpath(frappe.get_site_path("private", "files")),
        "backups": os.path.realpath(frappe.get_site_path("private", "backups")),
    }
