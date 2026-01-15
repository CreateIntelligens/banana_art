import sqlite3
import os

# Define path relative to the script execution location
# Assuming running from project root (or /app in docker)
DB_PATH = "backend/banana_art.db"

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
    print("Migration completed successfully.")

if __name__ == "__main__":
    migrate()
