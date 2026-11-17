"""In-process Frappe Framework + MariaDB runtime simulator for offline ERP-012 tests & CI conformance.

Models site-isolated databases, information_schema.COLUMNS, tabCustom Field, tabProperty Setter,
tabChange Engine Audit, tabChange Engine Blueprint State, tabUser, tabEmail Queue, tabWorkflow,
tabReport, DocPerm / permlevel enforcement in frappe.get_list, and MariaDB GET_LOCK / RELEASE_LOCK.

Used ONLY when explicitly requested via simulated factories (e.g. ``make_frappe_adapter(simulated=True)``
or ``make_frappe_harness()`` in CI). Production ``FrappeRuntimeBackend`` fails closed if real ``frappe``
is absent.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from types import SimpleNamespace
from typing import Any


class SimulatedPermissionError(PermissionError):
    """Equivalent to frappe.PermissionError for T36 and DocPerm checks."""


class SimulatedColumnDesc(dict):
    def __init__(self, name: str, type: str, default: Any = None, index: int = 0, unique: int = 0) -> None:
        super().__init__(name=name, type=type, default=default, index=int(bool(index)), unique=int(bool(unique)))

    def __getattr__(self, item: str) -> Any:
        try:
            return self[item]
        except KeyError as exc:
            raise AttributeError(item) from exc


def _std_columns() -> list[SimulatedColumnDesc]:
    return [
        SimulatedColumnDesc("name", "varchar(140)"),
        SimulatedColumnDesc("creation", "datetime(6)"),
        SimulatedColumnDesc("modified", "datetime(6)"),
        SimulatedColumnDesc("modified_by", "varchar(140)"),
        SimulatedColumnDesc("owner", "varchar(140)"),
        SimulatedColumnDesc("docstatus", "int(1)", default="0"),
        SimulatedColumnDesc("idx", "int(8)", default="0"),
    ]


_CORE_DOCTYPES: dict[str, dict[str, Any]] = {
    "Customer": {
        "issingle": 0,
        "fields": [
            {"fieldname": "customer_name", "fieldtype": "Data", "permlevel": 0},
            {"fieldname": "customer_type", "fieldtype": "Select", "permlevel": 0},
            {"fieldname": "tax_id", "fieldtype": "Data", "permlevel": 0},
        ],
        "perms": {
            "System Manager": {"read": 1, "write": 1, "create": 1},
            "owner": {"read": 1, "write": 1, "create": 1},
            "Sales User": {"read": 1, "write": 1, "create": 1},
            "sales_rep": {"read": 1, "write": 1, "create": 1},
            "accountant": {"read": 1, "write": 1},
        },
    },
    "Item": {
        "issingle": 0,
        "fields": [
            {"fieldname": "item_code", "fieldtype": "Data", "permlevel": 0},
            {"fieldname": "item_name", "fieldtype": "Data", "permlevel": 0},
            {"fieldname": "stock_uom", "fieldtype": "Link", "permlevel": 0},
            {"fieldname": "valuation_rate", "fieldtype": "Currency", "permlevel": 0},
            {"fieldname": "standard_rate", "fieldtype": "Currency", "permlevel": 0},
        ],
        "perms": {
            "System Manager": {"read": 1, "write": 1, "create": 1},
            "owner": {"read": 1, "write": 1, "create": 1},
            "Sales User": {"read": 1},
            "sales_rep": {"read": 1},
            "warehouse_keeper": {"read": 1},
            "Stock User": {"read": 1, "write": 1, "create": 1},
        },
    },
    "Sales Order": {
        "issingle": 0,
        "fields": [
            {"fieldname": "customer", "fieldtype": "Link", "permlevel": 0},
            {"fieldname": "transaction_date", "fieldtype": "Date", "permlevel": 0},
            {"fieldname": "grand_total", "fieldtype": "Currency", "permlevel": 0},
            {"fieldname": "workflow_state", "fieldtype": "Link", "permlevel": 0},
        ],
        "perms": {
            "System Manager": {"read": 1, "write": 1, "create": 1, "submit": 1},
            "owner": {"read": 1, "write": 1, "create": 1, "submit": 1},
            "Sales User": {"read": 1, "write": 1, "create": 1},
            "sales_rep": {"read": 1, "write": 1, "create": 1, "submit": 1},
        },
    },
    "Sales Order Item": {
        "issingle": 0,
        "fields": [{"fieldname": "item_code", "fieldtype": "Link", "permlevel": 0}, {"fieldname": "qty", "fieldtype": "Float", "permlevel": 0}],
        "perms": {"System Manager": {"read": 1, "write": 1, "create": 1}},
    },
    "Sales Invoice": {
        "issingle": 0,
        "fields": [
            {"fieldname": "customer", "fieldtype": "Link", "permlevel": 0},
            {"fieldname": "posting_date", "fieldtype": "Date", "permlevel": 0},
            {"fieldname": "grand_total", "fieldtype": "Currency", "permlevel": 0},
            {"fieldname": "outstanding_amount", "fieldtype": "Currency", "permlevel": 0},
        ],
        "perms": {
            "System Manager": {"read": 1, "write": 1, "create": 1, "submit": 1},
            "owner": {"read": 1, "write": 1, "create": 1, "submit": 1},
            "accountant": {"read": 1, "write": 1, "create": 1, "submit": 1},
            "Accounts User": {"read": 1, "write": 1, "create": 1, "submit": 1},
        },
    },
    "Sales Invoice Item": {
        "issingle": 0,
        "fields": [{"fieldname": "item_code", "fieldtype": "Link", "permlevel": 0}],
        "perms": {"System Manager": {"read": 1, "write": 1, "create": 1}},
    },
    "GL Entry": {
        "issingle": 0,
        "fields": [
            {"fieldname": "account", "fieldtype": "Link", "permlevel": 0},
            {"fieldname": "debit", "fieldtype": "Currency", "permlevel": 0},
            {"fieldname": "credit", "fieldtype": "Currency", "permlevel": 0},
        ],
        "perms": {"System Manager": {"read": 1}},
    },
    "Warehouse": {"issingle": 0, "fields": [{"fieldname": "warehouse_name", "fieldtype": "Data", "permlevel": 0}], "perms": {"System Manager": {"read": 1, "write": 1, "create": 1}}},
    "Company": {"issingle": 0, "fields": [{"fieldname": "company_name", "fieldtype": "Data", "permlevel": 0}, {"fieldname": "country", "fieldtype": "Link", "permlevel": 0}, {"fieldname": "default_currency", "fieldtype": "Link", "permlevel": 0}, {"fieldname": "tax_id", "fieldtype": "Data", "permlevel": 0}], "perms": {"System Manager": {"read": 1, "write": 1, "create": 1}}},
    "Stock Settings": {"issingle": 1, "fields": [{"fieldname": "valuation_method", "fieldtype": "Select", "permlevel": 0}, {"fieldname": "allow_negative_stock", "fieldtype": "Check", "permlevel": 0}], "perms": {"System Manager": {"read": 1, "write": 1}}},
    "System Settings": {"issingle": 1, "fields": [{"fieldname": "rounding_method", "fieldtype": "Select", "permlevel": 0}, {"fieldname": "language", "fieldtype": "Link", "permlevel": 0}, {"fieldname": "time_zone", "fieldtype": "Select", "permlevel": 0}, {"fieldname": "country", "fieldtype": "Link", "permlevel": 0}], "perms": {"System Manager": {"read": 1, "write": 1}}},
    "Accounts Settings": {"issingle": 1, "fields": [{"fieldname": "enable_immutable_ledger", "fieldtype": "Check", "permlevel": 0}], "perms": {"System Manager": {"read": 1, "write": 1}}},
    "Role": {"issingle": 0, "fields": [{"fieldname": "role_name", "fieldtype": "Data", "permlevel": 0}, {"fieldname": "disabled", "fieldtype": "Check", "permlevel": 0}], "perms": {"System Manager": {"read": 1, "write": 1, "create": 1}}},
    "User": {"issingle": 0, "fields": [{"fieldname": "email", "fieldtype": "Data", "permlevel": 0}, {"fieldname": "enabled", "fieldtype": "Check", "permlevel": 0}], "perms": {"System Manager": {"read": 1, "write": 1, "create": 1}}},
    "Custom Field": {"issingle": 0, "fields": [{"fieldname": "dt", "fieldtype": "Link", "permlevel": 0}, {"fieldname": "fieldname", "fieldtype": "Data", "permlevel": 0}], "perms": {"System Manager": {"read": 1, "write": 1, "create": 1}}},
    "Property Setter": {"issingle": 0, "fields": [{"fieldname": "doc_type", "fieldtype": "Link", "permlevel": 0}, {"fieldname": "field_name", "fieldtype": "Data", "permlevel": 0}, {"fieldname": "property", "fieldtype": "Data", "permlevel": 0}, {"fieldname": "value", "fieldtype": "Text", "permlevel": 0}], "perms": {"System Manager": {"read": 1, "write": 1, "create": 1}}},
    "Workflow": {"issingle": 0, "fields": [{"fieldname": "workflow_name", "fieldtype": "Data", "permlevel": 0}, {"fieldname": "document_type", "fieldtype": "Link", "permlevel": 0}, {"fieldname": "is_active", "fieldtype": "Check", "permlevel": 0}], "perms": {"System Manager": {"read": 1, "write": 1, "create": 1}}},
    "Workflow State": {"issingle": 0, "fields": [{"fieldname": "workflow_state_name", "fieldtype": "Data", "permlevel": 0}, {"fieldname": "style", "fieldtype": "Data", "permlevel": 0}], "perms": {"System Manager": {"read": 1, "write": 1, "create": 1}}},
    "Workflow Action Master": {"issingle": 0, "fields": [{"fieldname": "workflow_action_name", "fieldtype": "Data", "permlevel": 0}], "perms": {"System Manager": {"read": 1, "write": 1, "create": 1}}},
    "Report": {"issingle": 0, "fields": [{"fieldname": "report_name", "fieldtype": "Data", "permlevel": 0}, {"fieldname": "ref_doctype", "fieldtype": "Link", "permlevel": 0}, {"fieldname": "disabled", "fieldtype": "Check", "permlevel": 0}], "perms": {"System Manager": {"read": 1, "write": 1, "create": 1}}},
    "ToDo": {"issingle": 0, "fields": [{"fieldname": "description", "fieldtype": "Text", "permlevel": 0}], "perms": {"System Manager": {"read": 1, "write": 1, "create": 1}}},
    "Note": {"issingle": 0, "fields": [{"fieldname": "title", "fieldtype": "Data", "permlevel": 0}], "perms": {"System Manager": {"read": 1, "write": 1, "create": 1}}},
}

_FIELDTYPE_TO_SQL = {
    "Data": "varchar(140)",
    "Small Text": "text",
    "Text": "text",
    "Int": "int(11)",
    "Float": "decimal(21,9)",
    "Currency": "decimal(21,9)",
    "Percent": "decimal(21,9)",
    "Check": "int(1)",
    "Date": "date",
    "Datetime": "datetime(6)",
    "Select": "varchar(140)",
    "Link": "varchar(140)",
    "Phone": "varchar(140)",
}


class SimulatedDocument:
    """Simulated Frappe Document with insert/save/update/as_dict."""

    def __init__(self, site_db: "SimulatedSiteDB", data: dict[str, Any], is_new: bool = False) -> None:
        object.__setattr__(self, "_site_db", site_db)
        object.__setattr__(self, "_data", copy.deepcopy(data))
        object.__setattr__(self, "_is_new", is_new)

    def __getattr__(self, item: str) -> Any:
        data = object.__getattribute__(self, "_data")
        if item in data:
            return data[item]
        return None

    def __setattr__(self, item: str, value: Any) -> None:
        data = object.__getattribute__(self, "_data")
        data[item] = value

    def update(self, values: dict[str, Any]) -> None:
        data = object.__getattribute__(self, "_data")
        data.update(copy.deepcopy(values))

    def as_dict(self) -> dict[str, Any]:
        return copy.deepcopy(object.__getattribute__(self, "_data"))

    def insert(self, ignore_permissions: bool = False) -> "SimulatedDocument":
        site_db: SimulatedSiteDB = object.__getattribute__(self, "_site_db")
        data: dict[str, Any] = object.__getattribute__(self, "_data")
        if not ignore_permissions:
            site_db.runtime.require_perm(data["doctype"], "create")
        site_db.upsert_doc(data, is_insert=True)
        object.__setattr__(self, "_is_new", False)
        return self

    def save(self, ignore_permissions: bool = False) -> "SimulatedDocument":
        site_db: SimulatedSiteDB = object.__getattribute__(self, "_site_db")
        data: dict[str, Any] = object.__getattribute__(self, "_data")
        if not ignore_permissions:
            site_db.runtime.require_perm(data["doctype"], "write")
        site_db.upsert_doc(data, is_insert=False)
        object.__setattr__(self, "_is_new", False)
        return self


class SimulatedSiteDB:
    """Isolated per-tenant database state modeling MariaDB + Frappe metadata."""

    def __init__(self, site_name: str, runtime: "SimulatedFrappeRuntime") -> None:
        self.site_name = site_name
        self.runtime = runtime
        self.locks: set[str] = set()
        self.lock_wait_timeout: int = 5
        self.ddl_statements: list[str] = []
        self.doctype_meta: dict[str, dict[str, Any]] = copy.deepcopy(_CORE_DOCTYPES)
        self.table_columns: dict[str, list[SimulatedColumnDesc]] = {}
        self.rows: dict[str, dict[str, dict[str, Any]]] = {}
        self.singles: dict[str, dict[str, Any]] = {
            "Stock Settings": {"valuation_method": "FIFO", "allow_negative_stock": 0},
            "System Settings": {"rounding_method": "Banker's Rounding (legacy)", "language": "en", "time_zone": "UTC", "country": "United States"},
            "Accounts Settings": {"enable_immutable_ledger": 0},
        }
        self.auth_table: dict[str, str] = {}
        self.email_queue: list[dict[str, Any]] = []
        self.cleared_caches: list[str] = []
        self._init_core_tables()

    def _init_core_tables(self) -> None:
        for dt, spec in self.doctype_meta.items():
            if spec.get("issingle"):
                continue
            tbl = f"tab{dt}"
            cols = _std_columns()
            for f in spec.get("fields", []):
                ftype = _FIELDTYPE_TO_SQL.get(f["fieldtype"], "varchar(140)")
                cols.append(SimulatedColumnDesc(f["fieldname"], ftype))
            self.table_columns[tbl] = cols
            self.rows.setdefault(tbl, {})
        for extra_tbl in (
            "tabDocType",
            "tabCustom Field",
            "tabProperty Setter",
            "tabWorkflow",
            "tabWorkflow State",
            "tabWorkflow Action Master",
            "tabReport",
            "tabRole",
            "tabUser",
            "tabEmail Queue",
            "tabChange Engine Audit",
            "tabChange Engine Blueprint State",
        ):
            self.table_columns.setdefault(extra_tbl, _std_columns())
            self.rows.setdefault(extra_tbl, {})

    def _table_name(self, doctype: str) -> str:
        return doctype if doctype.startswith("tab") else f"tab{doctype}"

    def _doc_name(self, doctype: str, data: dict[str, Any]) -> str:
        if data.get("name"):
            return str(data["name"])
        if doctype == "Custom Field":
            return f"{data['dt']}-{data['fieldname']}"
        if doctype == "Property Setter":
            return f"{data['doc_type']}-{data.get('field_name') or ''}-{data['property']}"
        if doctype == "User":
            return str(data.get("email") or data.get("name"))
        if doctype == "Role":
            return str(data.get("role_name") or data.get("name"))
        if doctype == "Workflow":
            return str(data.get("workflow_name") or data.get("name"))
        if doctype == "Workflow State":
            return str(data.get("workflow_state_name") or data.get("name"))
        if doctype == "Workflow Action Master":
            return str(data.get("workflow_action_name") or data.get("name"))
        if doctype == "Report":
            return str(data.get("report_name") or data.get("name"))
        if doctype == "Company":
            return str(data.get("company_name") or data.get("name") or "Company")
        if doctype == "Warehouse":
            return str(data.get("warehouse_name") or data.get("name") or "Warehouse")
        if doctype == "DocType":
            return str(data.get("name"))
        return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:12]

    def upsert_doc(self, data: dict[str, Any], is_insert: bool) -> dict[str, Any]:
        dt = data["doctype"]
        if dt in self.singles:
            rec = self.singles[dt]
            for k, v in data.items():
                if k != "doctype":
                    rec[k] = v
            return copy.deepcopy(rec)

        name = self._doc_name(dt, data)
        doc = copy.deepcopy(data)
        doc["name"] = name
        tbl = f"tab{dt}"
        self.rows.setdefault(tbl, {})
        self.table_columns.setdefault(tbl, _std_columns())

        if dt == "Custom Field":
            target_dt = doc["dt"]
            target_tbl = f"tab{target_dt}"
            fname = doc["fieldname"]
            ftype = doc.get("fieldtype", "Data")
            sql_t = _FIELDTYPE_TO_SQL.get(ftype, "varchar(140)")
            self.table_columns.setdefault(target_tbl, _std_columns())
            if not any(c.name == fname for c in self.table_columns[target_tbl]):
                stmt = f"ALTER TABLE `{target_tbl}` ADD COLUMN `{fname}` {sql_t}"
                self.ddl_statements.append(stmt)
                self.table_columns[target_tbl].append(SimulatedColumnDesc(fname, sql_t))
        elif dt == "DocType":
            target_dt = name
            target_tbl = f"tab{target_dt}"
            fields = doc.get("fields") or []
            self.doctype_meta[target_dt] = {
                "issingle": int(bool(doc.get("issingle", 0))),
                "fields": copy.deepcopy(fields),
                "perms": {"System Manager": {"read": 1, "write": 1, "create": 1}, "owner": {"read": 1, "write": 1, "create": 1}},
            }
            if not self.doctype_meta[target_dt]["issingle"]:
                cols = list(self.table_columns.get(target_tbl, _std_columns()))
                for f in fields:
                    fn = f.get("fieldname")
                    if fn and not any(c.name == fn for c in cols):
                        cols.append(SimulatedColumnDesc(fn, _FIELDTYPE_TO_SQL.get(f.get("fieldtype", "Data"), "varchar(140)")))
                self.table_columns[target_tbl] = cols
                self.rows.setdefault(target_tbl, {})
        elif dt == "User":
            if doc.get("new_password"):
                self.auth_table[name] = "hashed"
            if doc.get("send_welcome_email"):
                self.email_queue.append({"recipient": name, "subject": "Welcome"})
            doc.setdefault("enabled", 1)
            doc.setdefault("roles", [])

        self.rows[tbl][name] = doc
        return doc


class SimulatedFrappeDB:
    """Exposed as ``frappe.db`` on SimulatedFrappeRuntime."""

    def __init__(self, runtime: "SimulatedFrappeRuntime") -> None:
        self._rt = runtime

    @property
    def _site(self) -> SimulatedSiteDB:
        return self._rt.current_site_db()

    def table_exists(self, doctype: str) -> bool:
        tbl = doctype if doctype.startswith("tab") else f"tab{doctype}"
        return tbl in self._site.table_columns

    def get_table_columns_description(self, table_name: str) -> list[SimulatedColumnDesc]:
        tbl = table_name if table_name.startswith("tab") else f"tab{table_name}"
        return list(self._site.table_columns.get(tbl, _std_columns()))

    def exists(self, doctype: str, name_or_filters: Any = None) -> Any:
        site = self._site
        if doctype in site.singles:
            return doctype
        tbl = f"tab{doctype}"
        rows = site.rows.get(tbl, {})
        if isinstance(name_or_filters, dict):
            for n, r in rows.items():
                if all(r.get(k) == v for k, v in name_or_filters.items()):
                    return n
            return None
        return name_or_filters if name_or_filters in rows else None

    def get_value(self, doctype: str, filters: Any, fieldname: Any = "name", as_dict: bool = False) -> Any:
        site = self._site
        if doctype in site.singles:
            rec = site.singles[doctype]
            if isinstance(fieldname, list):
                return {f: rec.get(f) for f in fieldname} if as_dict else tuple(rec.get(f) for f in fieldname)
            return rec.get(fieldname)
        tbl = f"tab{doctype}"
        rows = site.rows.get(tbl, {})
        match = None
        if isinstance(filters, dict):
            for r in rows.values():
                if all(r.get(k) == v for k, v in filters.items()):
                    match = r
                    break
        else:
            match = rows.get(str(filters))
        if match is None:
            return None
        if isinstance(fieldname, list):
            if as_dict:
                return {f: match.get(f) for f in fieldname}
            return tuple(match.get(f) for f in fieldname)
        return match.get(fieldname)

    def set_value(self, doctype: str, name: str, fieldname: str, value: Any) -> None:
        site = self._site
        if doctype in site.singles:
            site.singles[doctype][fieldname] = value
            return
        tbl = f"tab{doctype}"
        if name in site.rows.get(tbl, {}):
            site.rows[tbl][name][fieldname] = value

    def sql_ddl(self, query: str) -> None:
        self.sql(query)

    def sql(self, query: str, params: Any = None, as_dict: bool = False) -> Any:
        site = self._site
        q = " ".join(query.strip().split())
        q_upper = q.upper()
        p = tuple(params) if isinstance(params, (list, tuple)) else ()

        if q_upper == "SELECT 1":
            return [(1,)]

        if "GET_LOCK(" in q_upper:
            lock_key = str(p[0])
            if lock_key in site.locks:
                return [(0,)]
            site.locks.add(lock_key)
            return [(1,)]

        if "RELEASE_LOCK(" in q_upper:
            lock_key = str(p[0])
            site.locks.discard(lock_key)
            return [(1,)]

        if q_upper.startswith("SET SESSION LOCK_WAIT_TIMEOUT"):
            m = re.search(r"=\s*(\d+)", q)
            if m:
                site.lock_wait_timeout = int(m.group(1))
            return ()

        if q_upper.startswith("CREATE TABLE IF NOT EXISTS"):
            m = re.match(r"CREATE TABLE IF NOT EXISTS `([^`]+)`", q, flags=re.IGNORECASE)
            if m:
                tbl = m.group(1)
                site.table_columns.setdefault(tbl, _std_columns())
                site.rows.setdefault(tbl, {})
            return ()

        if "FROM INFORMATION_SCHEMA.COLUMNS" in q_upper:
            table_name = p[0] if p else ""
            cols = site.table_columns.get(table_name, [])
            if len(p) >= 2:
                col_name = p[1]
                cols = [c for c in cols if c.name == col_name]
            if "IS_NULLABLE" in q_upper:
                return [(c.name, c.type, "YES", c.default) for c in cols]
            if "COLUMN_NAME, COLUMN_TYPE, COLUMN_DEFAULT" in q_upper:
                return [(c.name, c.type, c.default) for c in cols]
            return [(c.name, c.type) for c in cols]

        if "FROM `TABCUSTOM FIELD`" in q_upper:
            dt, fn = p[0], p[1]
            row = next(
                (r for r in site.rows["tabCustom Field"].values() if r.get("dt") == dt and r.get("fieldname") == fn),
                None,
            )
            if row is None:
                return []
            if as_dict:
                return [copy.deepcopy(row)]
            return [(row["name"], row.get("fieldtype"))]

        if "FROM `TABPROPERTY SETTER`" in q_upper:
            rows = site.rows["tabProperty Setter"].values()
            if len(p) == 3:
                dt, fn, prop = p
                hit = [r for r in rows if r.get("doc_type") == dt and r.get("field_name") == fn and r.get("property") == prop]
            else:
                dt, prop = p
                hit = [r for r in rows if r.get("doc_type") == dt and not r.get("field_name") and r.get("property") == prop]
            if not hit:
                return []
            r = hit[0]
            return [copy.deepcopy(r)] if as_dict else [(r["name"], r.get("value"), r.get("property_type", "Data"))]

        if q_upper.startswith("DELETE FROM `TABPROPERTY SETTER`"):
            rows = site.rows["tabProperty Setter"]
            if len(p) == 3:
                dt, fn, prop = p
                doomed = [k for k, r in rows.items() if r.get("doc_type") == dt and r.get("field_name") == fn and r.get("property") == prop]
            else:
                dt, prop = p
                doomed = [k for k, r in rows.items() if r.get("doc_type") == dt and not r.get("field_name") and r.get("property") == prop]
            for k in doomed:
                del rows[k]
            return ()

        if "`TABCHANGE ENGINE AUDIT`" in q_upper:
            tbl = site.rows["tabChange Engine Audit"]
            if q_upper.startswith("INSERT INTO"):
                dep_id = p[0]
                rec = {
                    "name": dep_id,
                    "deployment_id": p[1],
                    "idempotency_key": p[2],
                    "payload_hash": p[3],
                    "site_id": p[4],
                    "doctype": p[5],
                    "fieldname": p[6],
                    "base_revision_hash": p[7],
                    "ddl_plan_statements": p[8],
                    "status": p[9],
                    "outcome_json": None,
                }
                tbl[dep_id] = rec
                return ()
            if q_upper.startswith("UPDATE"):
                status, outcome_json, dep_id = p
                if dep_id in tbl:
                    tbl[dep_id]["status"] = status
                    tbl[dep_id]["outcome_json"] = outcome_json
                return ()
            if "SELECT COUNT(*)" in q_upper:
                if "IN ('RECOVERY_REQUIRED', 'PREPARED')" in q_upper:
                    cnt = sum(1 for r in tbl.values() if r.get("status") in ("RECOVERY_REQUIRED", "PREPARED"))
                elif len(p) == 2:
                    site_id, dt = p
                    cnt = sum(
                        1 for r in tbl.values()
                        if r.get("site_id") == site_id and r.get("doctype") == dt and r.get("status") == "RECOVERY_REQUIRED"
                    )
                else:
                    cnt = sum(1 for r in tbl.values() if r.get("status") == "RECOVERY_REQUIRED")
                return [(cnt,)]
            if "SELECT PAYLOAD_HASH, OUTCOME_JSON" in q_upper:
                site_id, idemp = p
                for r in tbl.values():
                    if r.get("site_id") == site_id and r.get("idempotency_key") == idemp and r.get("outcome_json"):
                        return [(r["payload_hash"], r["outcome_json"])]
                return []
            if "WHERE DEPLOYMENT_ID = %S" in q_upper:
                dep_id = p[0]
                r = tbl.get(dep_id)
                if not r:
                    return []
                return [copy.deepcopy(r)] if as_dict else [tuple(r.values())]

        if "`TABCHANGE ENGINE BLUEPRINT STATE`" in q_upper:
            tbl = site.rows["tabChange Engine Blueprint State"]
            if q_upper.startswith("INSERT INTO"):
                tenant_id = p[0]
                tbl[tenant_id] = {
                    "tenant_id": tenant_id,
                    "state": p[1],
                    "site_class": p[2],
                    "engine_target_json": p[3],
                    "blueprint_id": p[4],
                    "country_pack": p[5],
                    "applied_json": p[6],
                    "applied_ids_json": p[7],
                    "history_json": p[8],
                    "sync_version": p[9],
                    "config_json": p[10],
                    "retained_json": p[11],
                }
                return ()
            if "WHERE TENANT_ID = %S" in q_upper:
                r = tbl.get(p[0])
                if not r:
                    return []
                return [copy.deepcopy(r)] if as_dict else [tuple(r.values())]
            if q_upper.startswith("DELETE FROM"):
                tbl.clear()
                return ()

        # Generic entity column read/write for tab<DocType> (data_probe & column queries)
        m_sel = re.match(r"SELECT `([^`]+)` FROM `([^`]+)` WHERE `name` = %s", q, flags=re.IGNORECASE)
        if m_sel:
            col, tbl = m_sel.group(1), m_sel.group(2)
            row = site.rows.get(tbl, {}).get(str(p[0]))
            if not row or col not in row:
                return []
            return [(row[col],)]

        m_ins = re.match(
            r"INSERT INTO `([^`]+)` \(`name`, `([^`]+)`\) VALUES \(%s, %s\) ON DUPLICATE KEY UPDATE",
            q,
            flags=re.IGNORECASE,
        )
        if m_ins:
            tbl, col = m_ins.group(1), m_ins.group(2)
            row_id, val = str(p[0]), p[1]
            site.rows.setdefault(tbl, {}).setdefault(row_id, {"name": row_id})[col] = val
            return ()

        return ()

    def commit(self) -> None:
        return None

    def rollback(self) -> None:
        return None


class SimulatedMeta:
    def __init__(self, site: SimulatedSiteDB, doctype: str) -> None:
        self._site = site
        self.name = doctype
        spec = site.doctype_meta.get(doctype, {"issingle": 0, "fields": []})
        self.issingle = spec.get("issingle", 0)
        self._fields = self._build_fields(spec.get("fields", []), doctype)

    def _build_fields(self, base_fields: list[dict[str, Any]], doctype: str) -> list[SimpleNamespace]:
        by_name: dict[str, dict[str, Any]] = {}
        for f in base_fields:
            by_name[f["fieldname"]] = dict(f)
        for r in self._site.rows.get("tabCustom Field", {}).values():
            if r.get("dt") == doctype:
                by_name[r["fieldname"]] = dict(r)
        for r in self._site.rows.get("tabProperty Setter", {}).values():
            if r.get("doc_type") == doctype and r.get("field_name") in by_name:
                prop = r["property"]
                val = r["value"]
                if prop in ("permlevel", "hidden", "reqd", "read_only"):
                    val = int(val)
                by_name[r["field_name"]][prop] = val
        return [SimpleNamespace(**fd) for fd in by_name.values()]

    @property
    def fields(self) -> list[SimpleNamespace]:
        return self._fields

    def get_field(self, fieldname: str) -> SimpleNamespace | None:
        for f in self._fields:
            if getattr(f, "fieldname", None) == fieldname:
                return f
        return None


class SimulatedFrappeRuntime:
    """Thread/instance-local Frappe runtime simulator supporting multi-site isolation."""

    PermissionError = SimulatedPermissionError

    def __init__(self) -> None:
        self.sites: dict[str, SimulatedSiteDB] = {}
        self.local = SimpleNamespace(site=None)
        self.session = SimpleNamespace(user="Administrator")
        self.db = SimulatedFrappeDB(self)

    def current_site_db(self) -> SimulatedSiteDB:
        site_name = self.local.site
        if not site_name or site_name not in self.sites:
            raise RuntimeError(f"Unknown or unconnected site: {site_name}")
        return self.sites[site_name]

    def ensure_site(self, site_name: str) -> SimulatedSiteDB:
        if site_name not in self.sites:
            self.sites[site_name] = SimulatedSiteDB(site_name, self)
        return self.sites[site_name]

    def init(self, site: str, sites_path: str | None = None) -> None:
        self.local.site = site

    def connect(self, site: str | None = None) -> None:
        if site:
            self.local.site = site
        if self.local.site not in self.sites:
            raise RuntimeError(f"Site not initialized: {self.local.site}")

    def destroy(self) -> None:
        self.local.site = None
        self.session.user = "Administrator"

    def set_user(self, user: str) -> None:
        self.session.user = user

    def get_roles(self, user: str | None = None) -> list[str]:
        target = user or self.session.user
        if target == "Administrator":
            return ["System Manager", "Administrator", "All"]
        if target == "Guest":
            return ["Guest"]
        site = self.current_site_db()
        u = site.rows["tabUser"].get(target)
        if not u or not int(u.get("enabled", 0)):
            return []
        roles = [r["role"] if isinstance(r, dict) else str(r) for r in u.get("roles", [])]
        return list(dict.fromkeys(roles + ["All"]))

    def require_perm(self, doctype: str, ptype: str = "read") -> None:
        roles = set(self.get_roles())
        if "System Manager" in roles:
            return
        spec = self.current_site_db().doctype_meta.get(doctype, {})
        perms = spec.get("perms", {})
        for role in roles:
            if perms.get(role, {}).get(ptype):
                return
        raise SimulatedPermissionError(f"User lacks {ptype} permission for DocType {doctype}")

    def get_meta(self, doctype: str) -> SimulatedMeta:
        return SimulatedMeta(self.current_site_db(), doctype)

    def clear_cache(self, doctype: str | None = None) -> None:
        site = self.current_site_db()
        if doctype:
            site.cleared_caches.append(doctype)

    def get_doc(self, arg1: Any, arg2: str | None = None) -> SimulatedDocument:
        site = self.current_site_db()
        if isinstance(arg1, dict):
            return SimulatedDocument(site, arg1, is_new=True)
        doctype = str(arg1)
        if doctype in site.singles:
            data = {"doctype": doctype, **site.singles[doctype]}
            return SimulatedDocument(site, data, is_new=False)
        name = str(arg2)
        tbl = f"tab{doctype}"
        row = site.rows.get(tbl, {}).get(name)
        if row is None:
            raise KeyError(f"{doctype} {name} not found")
        return SimulatedDocument(site, row, is_new=False)

    def get_all(self, doctype: str, fields: list[str] | None = None, filters: dict[str, Any] | None = None, **_: Any) -> list[dict[str, Any]]:
        site = self.current_site_db()
        tbl = f"tab{doctype}"
        out = []
        for r in site.rows.get(tbl, {}).values():
            if filters and not all(r.get(k) == v for k, v in filters.items()):
                continue
            if fields:
                out.append({f: r.get(f) for f in fields if f in r})
            else:
                out.append(copy.deepcopy(r))
        return out

    def get_list(self, doctype: str, fields: list[str] | None = None, filters: dict[str, Any] | None = None, **kwargs: Any) -> list[dict[str, Any]]:
        self.require_perm(doctype, "read")
        roles = set(self.get_roles())
        meta = self.get_meta(doctype)
        blocked_fields: set[str] = set()
        if "System Manager" not in roles:
            for f in meta.fields:
                if int(getattr(f, "permlevel", 0) or 0) > 0:
                    blocked_fields.add(f.fieldname)
        rows = self.get_all(doctype, fields=fields, filters=filters, **kwargs)
        if blocked_fields:
            for r in rows:
                for bf in blocked_fields:
                    r.pop(bf, None)
        return rows

    def make_property_setter(self, args: dict[str, Any] | None = None, **kwargs: Any) -> SimulatedDocument:
        payload = dict(args if isinstance(args, dict) else kwargs)
        doc = {
            "doctype": "Property Setter",
            "doc_type": payload["doctype"],
            "field_name": payload.get("fieldname"),
            "property": payload["property"],
            "value": payload["value"],
            "property_type": payload.get("property_type", "Data"),
        }
        return self.get_doc(doc).insert(ignore_permissions=True)


__all__ = ["SimulatedFrappeRuntime", "SimulatedPermissionError"]
