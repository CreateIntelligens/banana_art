import sqlite3
import os

# Define path relative to the script execution location
# Assuming running from project root (or /app in docker)
DB_PATH = "backend/banana_art.db"

# Tables whose INTEGER PRIMARY KEY needs AUTOINCREMENT so that SQLite never
# reissues the id of a deleted row (default SQLite rowid behavior otherwise
# reuses "current max id + 1", which can hand out a freshly-deleted id to an
# unrelated new row). Each entry: (table_name, full CREATE TABLE body incl.
# AUTOINCREMENT, ordered column list for the data copy, list of non-PK index
# CREATE statements to restore afterwards).
_AUTOINCREMENT_TABLES = [
    (
        "uploaded_images",
        """
        CREATE TABLE uploaded_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename VARCHAR,
            filepath VARCHAR,
            upload_time DATETIME DEFAULT CURRENT_TIMESTAMP,
            is_hidden BOOLEAN DEFAULT 0
        )
        """,
        ["id", "filename", "filepath", "upload_time", "is_hidden"],
        ["CREATE INDEX ix_uploaded_images_filename ON uploaded_images (filename)"],
    ),
    (
        "templates",
        """
        CREATE TABLE templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR,
            prompt_template TEXT,
            aspect_ratio VARCHAR,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """,
        ["id", "name", "prompt_template", "aspect_ratio", "created_at"],
        ["CREATE INDEX ix_templates_name ON templates (name)"],
    ),
    (
        "generations",
        """
        CREATE TABLE generations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prompt TEXT,
            source_image_id INTEGER,
            aspect_ratio VARCHAR,
            output_image_path VARCHAR,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME,
            started_at DATETIME,
            FOREIGN KEY(source_image_id) REFERENCES uploaded_images (id)
        )
        """,
        ["id", "prompt", "source_image_id", "aspect_ratio", "output_image_path", "created_at", "completed_at", "started_at"],
        [],
    ),
]

# Many-to-many association tables. These have no id/AUTOINCREMENT of their own,
# but SQLite silently rewrites their FOREIGN KEY text to point at the *_old
# table whenever one of the tables above gets renamed mid-migration, leaving
# them referencing a table name that no longer exists once the old table is
# dropped. Harmless while PRAGMA foreign_keys is off (as in this app), but
# rebuilt here for correctness after any of the tables above is migrated.
_ASSOCIATION_TABLES = [
    (
        "generation_inputs",
        """
        CREATE TABLE generation_inputs (
            generation_id INTEGER,
            uploaded_image_id INTEGER,
            FOREIGN KEY(generation_id) REFERENCES generations (id),
            FOREIGN KEY(uploaded_image_id) REFERENCES uploaded_images (id)
        )
        """,
        ["generation_id", "uploaded_image_id"],
    ),
    (
        "template_inputs",
        """
        CREATE TABLE template_inputs (
            template_id INTEGER,
            uploaded_image_id INTEGER,
            FOREIGN KEY(template_id) REFERENCES templates (id),
            FOREIGN KEY(uploaded_image_id) REFERENCES uploaded_images (id)
        )
        """,
        ["template_id", "uploaded_image_id"],
    ),
]


def _table_has_autoincrement(cursor, table):
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,))
    row = cursor.fetchone()
    return bool(row and row[0] and "AUTOINCREMENT" in row[0].upper())


def _fk_targets_current_tables(cursor, table):
    """True if every FK on `table` points at a table that actually exists (not a stale '<x>_old' name)."""
    cursor.execute(f"PRAGMA foreign_key_list({table})")
    for row in cursor.fetchall():
        target_table = row[2]
        cursor.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (target_table,))
        if not cursor.fetchone():
            return False
    return True


def _rebuild_table(cursor, table, create_sql, columns, post_sqls):
    """
    Rename `table` out of the way, recreate it from create_sql, copy all rows
    across, verify the row count matches, then drop the renamed original and
    run post_sqls (e.g. index recreation). Raises on any row-count mismatch.
    Must be called inside an already-open transaction (isolation_level=None,
    caller issues BEGIN/COMMIT/ROLLBACK) so a failure can be rolled back in
    full, including the ALTER/CREATE/INSERT steps.
    """
    old_table = f"{table}__migrating"
    cursor.execute(f"DROP TABLE IF EXISTS {old_table}")

    cursor.execute(f"SELECT COUNT(*) FROM {table}")
    before_count = cursor.fetchone()[0]

    cursor.execute(f"ALTER TABLE {table} RENAME TO {old_table}")
    cursor.execute(create_sql)

    col_list = ", ".join(columns)
    cursor.execute(f"INSERT INTO {table} ({col_list}) SELECT {col_list} FROM {old_table}")

    cursor.execute(f"SELECT COUNT(*) FROM {table}")
    after_count = cursor.fetchone()[0]
    if after_count != before_count:
        raise RuntimeError(f"Row count mismatch migrating '{table}': before={before_count}, after={after_count}")

    # Drop the old table *before* recreating indexes: SQLite keeps the old
    # table's indexes alive (under their original names) across the RENAME,
    # so creating a same-named index while the renamed table still exists
    # collides with it.
    cursor.execute(f"DROP TABLE {old_table}")

    for sql in post_sqls:
        cursor.execute(sql)

    return after_count


def migrate_autoincrement(db_path):
    """
    Rebuild id columns with AUTOINCREMENT so deleted ids are never reissued,
    and repair association-table foreign keys that SQLite silently repoints
    at the pre-migration table names in the process. Safe to run repeatedly:
    each table is skipped once it already has AUTOINCREMENT / correct FKs.

    Runs its own connection in autocommit mode (isolation_level=None) with an
    explicit BEGIN/COMMIT/ROLLBACK per table so that, on failure, every step
    (including the ALTER TABLE / CREATE TABLE) is genuinely rolled back
    rather than silently left half-applied.
    """
    conn = sqlite3.connect(db_path, isolation_level=None)
    cursor = conn.cursor()

    migrated_any = False
    for table, create_sql, columns, index_sqls in _AUTOINCREMENT_TABLES:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
        if not cursor.fetchone():
            print(f"Table '{table}' does not exist yet. Skipping AUTOINCREMENT migration (will be created by app).")
            continue

        if _table_has_autoincrement(cursor, table):
            print(f"Table '{table}' already uses AUTOINCREMENT.")
            continue

        print(f"Migrating '{table}' to AUTOINCREMENT (prevents id reuse after delete)...")
        try:
            cursor.execute("BEGIN")
            row_count = _rebuild_table(cursor, table, create_sql, columns, index_sqls)
            cursor.execute("COMMIT")
            migrated_any = True
            print(f"'{table}' migrated successfully ({row_count} rows preserved, id reuse now prevented).")
        except Exception as e:
            cursor.execute("ROLLBACK")
            print(f"Error migrating '{table}' to AUTOINCREMENT: {e}. '{table}' left unchanged.")

    # Repair association-table FKs left pointing at renamed tables by the
    # migration above (only relevant the first time this ever runs).
    for table, create_sql, columns in _ASSOCIATION_TABLES:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
        if not cursor.fetchone():
            continue
        if _fk_targets_current_tables(cursor, table):
            continue

        print(f"Repairing foreign keys on '{table}' (still pointing at pre-migration table names)...")
        try:
            cursor.execute("BEGIN")
            row_count = _rebuild_table(cursor, table, create_sql, columns, [])
            cursor.execute("COMMIT")
            print(f"'{table}' foreign keys repaired ({row_count} rows preserved).")
        except Exception as e:
            cursor.execute("ROLLBACK")
            print(f"Error repairing foreign keys on '{table}': {e}. '{table}' left unchanged.")

    conn.close()
    return migrated_any


def migrate():
    # Handle path variations (local vs docker vs different cwd)
    target_db = DB_PATH
    if not os.path.exists(target_db):
        if os.path.exists("banana_art.db"):
            target_db = "banana_art.db"
        elif os.path.exists(os.path.join(os.path.dirname(__file__), "banana_art.db")):
            target_db = os.path.join(os.path.dirname(__file__), "banana_art.db")
        else:
            print(f"Warning: Database file not found at {DB_PATH}. Creating a new one or skipping if managed by app.")
            # If DB doesn't exist, SQLAlchemy create_all will handle it later, but here we just exit
            return

    print(f"Migrating database: {target_db}")
    conn = sqlite3.connect(target_db)
    cursor = conn.cursor()

    # Get existing columns in 'generations' table
    try:
        cursor.execute("PRAGMA table_info(generations)")
        columns = [info[1] for info in cursor.fetchall()]
    except sqlite3.OperationalError:
        print("Table 'generations' does not exist. Skipping migration (will be created by app).")
        conn.close()
        return

    # Check and Add 'completed_at'
    if 'completed_at' not in columns:
        print("Adding column 'completed_at'...")
        try:
            cursor.execute("ALTER TABLE generations ADD COLUMN completed_at DATETIME")
            conn.commit()
            print("Done.")
        except Exception as e:
            print(f"Error adding completed_at: {e}")
    else:
        print("Column 'completed_at' already exists.")

    # Check and Add 'started_at'
    if 'started_at' not in columns:
        print("Adding column 'started_at'...")
        try:
            cursor.execute("ALTER TABLE generations ADD COLUMN started_at DATETIME")
            conn.commit()
            print("Done.")
        except Exception as e:
            print(f"Error adding started_at: {e}")
    else:
        print("Column 'started_at' already exists.")

    # --- Check uploaded_images table ---
    try:
        cursor.execute("PRAGMA table_info(uploaded_images)")
        img_columns = [info[1] for info in cursor.fetchall()]

        if 'is_hidden' not in img_columns:
            print("Adding column 'is_hidden' to uploaded_images...")
            try:
                cursor.execute("ALTER TABLE uploaded_images ADD COLUMN is_hidden BOOLEAN DEFAULT 0")
                conn.commit()
                print("Done.")
            except Exception as e:
                print(f"Error adding is_hidden: {e}")
        else:
            print("Column 'is_hidden' already exists.")

    except sqlite3.OperationalError:
        print("Table 'uploaded_images' check skipped (will be created by app).")

    conn.close()

    # --- Prevent id reuse after delete (generations, uploaded_images, templates) ---
    migrate_autoincrement(target_db)

    print("Migration completed successfully.")

if __name__ == "__main__":
    migrate()
