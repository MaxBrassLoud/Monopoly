import sqlite3

DB_NAME = "database.db"

def get_connection():
    return sqlite3.connect(DB_NAME)

def create_database():
    conn = get_connection()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE,
        password TEXT,
        email TEXT UNIQUE,
        third_party INTEGER,
        provider INTEGER,
        user_id TEXT
    )
    """)

    conn.commit()
    conn.close()


def create_user(user_id, username, password, email, third_party=0, provider=0, ext_user_id=None):
    conn = get_connection()
    c = conn.cursor()

    try:
        c.execute("""
        INSERT INTO users (id, username, password, email, third_party, provider, user_id)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, username, password, email, third_party, provider, ext_user_id))

        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def get_user_by_username(username):
    conn = get_connection()
    c = conn.cursor()

    c.execute("SELECT * FROM users WHERE username = ?", (username,))
    user = c.fetchone()

    conn.close()
    return user