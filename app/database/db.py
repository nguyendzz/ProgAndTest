import os
import sqlite3
from contextlib import contextmanager


class DatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    @contextmanager
    def connection(self):
        conn = self.get_connection()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @contextmanager
    def atomic_transaction(self):
        conn = self.get_connection()
        conn.isolation_level = None
        try:
            conn.execute("BEGIN IMMEDIATE;")
            yield conn
            conn.execute("COMMIT;")
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK;")
            raise
        finally:
            conn.close()

    def init_schema(self):
        schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
        with open(schema_path, "r", encoding="utf-8") as f:
            schema_sql = f.read()
        with self.connection() as conn:
            conn.executescript(schema_sql)

    def seed_default_admin(self, password_hash: str):
        with self.connection() as conn:
            row = conn.execute(
                "SELECT UserID FROM USERS WHERE Username = ?", ("admin",)
            ).fetchone()
            if not row:
                conn.execute(
                    """
                    INSERT INTO USERS (Username, PasswordHash, Role, Status, Email)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    ("admin", password_hash, "Admin", "Active", "admin@school.edu"),
                )
