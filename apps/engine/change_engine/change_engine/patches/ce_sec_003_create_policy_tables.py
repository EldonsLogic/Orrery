"""CE-SEC-003: create the runtime policy and policy audit tables during `bench migrate`.

Tables are created here, never from a request or validate hook, because DDL commits the
open transaction. Idempotent (CREATE TABLE IF NOT EXISTS).
"""

import frappe

POLICY_TABLE = "tabChange Engine Policy"
AUDIT_TABLE = "tabChange Engine Policy Audit"


def execute():
    frappe.db.sql_ddl(f"""
        CREATE TABLE IF NOT EXISTS `{POLICY_TABLE}` (
            name VARCHAR(140) PRIMARY KEY,
            policy_id VARCHAR(140) NOT NULL,
            site_id VARCHAR(140) NOT NULL,
            doctype VARCHAR(140) NOT NULL,
            policy_type VARCHAR(64) NOT NULL,
            target_field VARCHAR(140),
            governance_tier INT DEFAULT 1,
            condition_expr TEXT,
            required_role VARCHAR(255),
            error_message TEXT,
            stage VARCHAR(64),
            active TINYINT DEFAULT 1,
            revision INT DEFAULT 1,
            created_by VARCHAR(140),
            created_at DATETIME(6),
            updated_by VARCHAR(140),
            updated_at DATETIME(6),
            UNIQUE KEY uq_site_policy (site_id, policy_id),
            INDEX idx_site_dt_act (site_id, doctype, active)
        ) ENGINE=InnoDB
    """)
    frappe.db.sql_ddl(f"""
        CREATE TABLE IF NOT EXISTS `{AUDIT_TABLE}` (
            name VARCHAR(140) PRIMARY KEY,
            audit_id VARCHAR(140) NOT NULL,
            site_id VARCHAR(140) NOT NULL,
            policy_id VARCHAR(140) NOT NULL,
            doctype VARCHAR(140) NOT NULL,
            revision INT NOT NULL,
            action VARCHAR(64) NOT NULL,
            changed_by VARCHAR(140),
            payload_before LONGTEXT,
            payload_after LONGTEXT,
            timestamp DATETIME(6),
            INDEX idx_site_pol (site_id, policy_id),
            INDEX idx_timestamp (timestamp)
        ) ENGINE=InnoDB
    """)
