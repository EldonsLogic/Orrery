"""Create the site outbox at install or migration time."""

from change_engine.adapter.record_events import OUTBOX_TABLE


def execute():
    """Keep implicit DDL commits outside document transactions."""
    import frappe

    frappe.db.sql_ddl(f"""
        CREATE TABLE IF NOT EXISTS `{OUTBOX_TABLE}` (
            position BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
            event_id CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NOT NULL UNIQUE,
            payload LONGTEXT NOT NULL
        ) ENGINE=InnoDB
    """)
