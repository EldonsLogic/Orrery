"""Create the site outbox and surrogate subject table at install or migration time."""

from change_engine.adapter.record_events import OUTBOX_TABLE, SUBJECT_TABLE


def execute():
    """Keep implicit DDL commits outside document transactions."""
    import frappe

    frappe.db.sql_ddl(f"""
        CREATE TABLE IF NOT EXISTS `{OUTBOX_TABLE}` (
            position BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
            event_id CHAR(26) CHARACTER SET ascii COLLATE ascii_bin NOT NULL UNIQUE,
            payload LONGTEXT NOT NULL,
            attempts INT UNSIGNED NOT NULL DEFAULT 0,
            last_error TEXT NULL,
            dead_lettered_at VARCHAR(32) NULL,
            INDEX idx_outbox_pending (dead_lettered_at, position)
        ) ENGINE=InnoDB
    """)
    for alter_stmt in (
        f"ALTER TABLE `{OUTBOX_TABLE}` ADD COLUMN IF NOT EXISTS attempts INT UNSIGNED NOT NULL DEFAULT 0",
        f"ALTER TABLE `{OUTBOX_TABLE}` ADD COLUMN IF NOT EXISTS last_error TEXT NULL",
        f"ALTER TABLE `{OUTBOX_TABLE}` ADD COLUMN IF NOT EXISTS dead_lettered_at VARCHAR(32) NULL",
    ):
        try:
            frappe.db.sql_ddl(alter_stmt)
        except Exception:
            pass

    frappe.db.sql_ddl(f"""
        CREATE TABLE IF NOT EXISTS `{SUBJECT_TABLE}` (
            subject_id VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL PRIMARY KEY,
            entity VARCHAR(64) NOT NULL,
            record_name VARCHAR(255) NOT NULL,
            deleted TINYINT(1) NOT NULL DEFAULT 0,
            UNIQUE KEY idx_entity_record (entity, record_name)
        ) ENGINE=InnoDB
    """)
