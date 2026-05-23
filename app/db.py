import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


STATUS_AWAITING_PROOF = "awaiting_payment_proof"
STATUS_PENDING_REVIEW = "pending_payment_review"
STATUS_CONFIRMED = "payment_confirmed"
STATUS_REJECTED = "rejected"
STATUS_IN_QUEUE = "in_queue"
STATUS_PROCESSING = "processing"
STATUS_DONE = "done"
STATUS_CANCELLED = "cancelled"


STATUS_LABELS = {
    STATUS_AWAITING_PROOF: "Awaiting Payment Proof",
    STATUS_PENDING_REVIEW: "Pending Payment Review",
    STATUS_CONFIRMED: "Payment Confirmed",
    STATUS_REJECTED: "Rejected",
    STATUS_IN_QUEUE: "In Queue",
    STATUS_PROCESSING: "Processing",
    STATUS_DONE: "Done",
    STATUS_CANCELLED: "Cancelled",
    "mock_paid": "Mock Paid",
    "pending": "Pending",
    "confirmed": "Confirmed",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def status_label(status: str | None) -> str:
    if not status:
        return "Unknown"
    return STATUS_LABELS.get(status, status)


class Database:
    def __init__(self, path: str) -> None:
        self.path = path

    def init(self) -> None:
        db_path = Path(self.path)
        if db_path.parent != Path("."):
            db_path.parent.mkdir(parents=True, exist_ok=True)

        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    telegram_user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    full_name TEXT,
                    phone_number TEXT,
                    is_vip INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    username TEXT,
                    full_name TEXT,
                    phone_number TEXT,
                    service_key TEXT NOT NULL,
                    service_title TEXT NOT NULL,
                    service_price TEXT NOT NULL,
                    amount_text TEXT,
                    payment_purpose TEXT,
                    customer_name TEXT,
                    customer_username TEXT,
                    customer_comment TEXT,
                    status TEXT NOT NULL DEFAULT 'awaiting_payment_proof',
                    created_at TEXT NOT NULL,
                    updated_at TEXT,
                    confirmed_at TEXT,
                    rejected_at TEXT,
                    queued_at TEXT,
                    processing_at TEXT,
                    done_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS payment_proofs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    file_id TEXT NOT NULL,
                    file_unique_id TEXT,
                    file_type TEXT NOT NULL,
                    mime_type TEXT,
                    file_name TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS admin_reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL,
                    admin_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    comment TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS vip_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'in_queue',
                    questionnaire TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    order_id INTEGER NOT NULL,
                    chat_id INTEGER,
                    invite_link TEXT,
                    starts_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    reminder_sent_at TEXT,
                    status TEXT NOT NULL DEFAULT 'active'
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS consultations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    questionnaire TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'in_queue',
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS legit_check (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    file_id TEXT NOT NULL,
                    file_unique_id TEXT,
                    file_type TEXT NOT NULL,
                    caption TEXT,
                    status TEXT NOT NULL DEFAULT 'in_queue',
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS buyout_orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    item_link TEXT NOT NULL,
                    item_price TEXT NOT NULL,
                    comment TEXT,
                    status TEXT NOT NULL DEFAULT 'awaiting_payment_proof',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

            self._migrate_existing_schema(conn)

    def _migrate_existing_schema(self, conn: sqlite3.Connection) -> None:
        order_columns = {
            "amount_text": "TEXT",
            "payment_purpose": "TEXT",
            "customer_name": "TEXT",
            "customer_username": "TEXT",
            "customer_comment": "TEXT",
            "updated_at": "TEXT",
            "confirmed_at": "TEXT",
            "rejected_at": "TEXT",
            "queued_at": "TEXT",
            "processing_at": "TEXT",
            "done_at": "TEXT",
        }
        for column, column_type in order_columns.items():
            self._ensure_column(conn, "orders", column, column_type)

        user_columns = {
            "phone_number": "TEXT",
            "is_vip": "INTEGER NOT NULL DEFAULT 0",
            "updated_at": "TEXT",
        }
        for column, column_type in user_columns.items():
            self._ensure_column(conn, "users", column, column_type)

    def upsert_user(
        self,
        *,
        telegram_user_id: int,
        username: str | None,
        full_name: str | None,
        phone_number: str | None = None,
    ) -> None:
        now = utc_now()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT telegram_user_id FROM users WHERE telegram_user_id = ?",
                (telegram_user_id,),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE users
                    SET username = ?, full_name = ?, phone_number = COALESCE(?, phone_number), updated_at = ?
                    WHERE telegram_user_id = ?
                    """,
                    (username, full_name, phone_number, now, telegram_user_id),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO users (
                        telegram_user_id, username, full_name, phone_number,
                        is_vip, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, 0, ?, ?)
                    """,
                    (telegram_user_id, username, full_name, phone_number, now, now),
                )

    def is_user_vip(self, user_id: int) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT is_vip FROM users WHERE telegram_user_id = ?",
                (user_id,),
            ).fetchone()
            return bool(row and row["is_vip"])

    def mark_user_vip(self, user_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE users SET is_vip = 1, updated_at = ? WHERE telegram_user_id = ?",
                (utc_now(), user_id),
            )

    def create_order(
        self,
        *,
        user_id: int,
        username: str | None,
        full_name: str,
        service_key: str,
        service_title: str,
        service_price: str,
        amount_text: str | None = None,
    ) -> int:
        now = utc_now()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO orders (
                    user_id, username, full_name, service_key,
                    service_title, service_price, amount_text, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    username,
                    full_name,
                    service_key,
                    service_title,
                    service_price,
                    amount_text or service_price,
                    STATUS_AWAITING_PROOF,
                    now,
                    now,
                ),
            )
            order_id = int(cursor.lastrowid)
            conn.execute(
                "UPDATE orders SET payment_purpose = ? WHERE id = ?",
                (self.build_payment_purpose(order_id), order_id),
            )
            return order_id

    @staticmethod
    def build_payment_purpose(order_id: int) -> str:
        return f"VCOMM-{order_id}"

    def get_order(self, order_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
            return dict(row) if row else None

    def update_order_contact(
        self,
        order_id: int,
        *,
        customer_name: str | None = None,
        customer_username: str | None = None,
        phone_number: str | None = None,
        customer_comment: str | None = None,
    ) -> None:
        fields: list[str] = []
        values: list[Any] = []
        updates = {
            "customer_name": customer_name,
            "customer_username": customer_username,
            "phone_number": phone_number,
            "customer_comment": customer_comment,
        }
        for column, value in updates.items():
            if value is not None:
                fields.append(f"{column} = ?")
                values.append(value)
        if not fields:
            return
        fields.append("updated_at = ?")
        values.append(utc_now())
        values.append(order_id)
        with self._connect() as conn:
            conn.execute(f"UPDATE orders SET {', '.join(fields)} WHERE id = ?", values)
            if phone_number:
                row = conn.execute("SELECT user_id FROM orders WHERE id = ?", (order_id,)).fetchone()
                if row:
                    conn.execute(
                        "UPDATE users SET phone_number = ?, updated_at = ? WHERE telegram_user_id = ?",
                        (phone_number, utc_now(), row["user_id"]),
                    )

    def update_order_phone(self, order_id: int, phone_number: str) -> None:
        self.update_order_contact(order_id, phone_number=phone_number)

    def update_order_status(self, order_id: int, status: str) -> None:
        timestamp_column = {
            STATUS_CONFIRMED: "confirmed_at",
            STATUS_REJECTED: "rejected_at",
            STATUS_IN_QUEUE: "queued_at",
            STATUS_PROCESSING: "processing_at",
            STATUS_DONE: "done_at",
        }.get(status)
        fields = ["status = ?", "updated_at = ?"]
        values: list[Any] = [status, utc_now()]
        if timestamp_column:
            fields.append(f"{timestamp_column} = COALESCE({timestamp_column}, ?)")
            values.append(utc_now())
        values.append(order_id)
        with self._connect() as conn:
            conn.execute(f"UPDATE orders SET {', '.join(fields)} WHERE id = ?", values)

    def create_payment_proof(
        self,
        *,
        order_id: int,
        user_id: int,
        file_id: str,
        file_unique_id: str | None,
        file_type: str,
        mime_type: str | None = None,
        file_name: str | None = None,
    ) -> int:
        now = utc_now()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO payment_proofs (
                    order_id, user_id, file_id, file_unique_id, file_type,
                    mime_type, file_name, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (order_id, user_id, file_id, file_unique_id, file_type, mime_type, file_name, now),
            )
            return int(cursor.lastrowid)

    def get_latest_payment_proof(self, order_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM payment_proofs
                WHERE order_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (order_id,),
            ).fetchone()
            return dict(row) if row else None

    def add_admin_review(self, *, order_id: int, admin_id: int, action: str, comment: str | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO admin_reviews (order_id, admin_id, action, comment, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (order_id, admin_id, action, comment, utc_now()),
            )

    def create_consultation(self, *, order_id: int, user_id: int, questionnaire: str) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO consultations (order_id, user_id, questionnaire, status, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (order_id, user_id, questionnaire, STATUS_IN_QUEUE, utc_now()),
            )
            return int(cursor.lastrowid)

    def add_legit_check_file(
        self,
        *,
        order_id: int,
        user_id: int,
        file_id: str,
        file_unique_id: str | None,
        file_type: str,
        caption: str | None,
    ) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO legit_check (
                    order_id, user_id, file_id, file_unique_id, file_type,
                    caption, status, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (order_id, user_id, file_id, file_unique_id, file_type, caption, STATUS_IN_QUEUE, utc_now()),
            )
            return int(cursor.lastrowid)

    def get_legit_check_files(self, order_id: int) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM legit_check WHERE order_id = ? ORDER BY id",
                (order_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def create_vip_queue(self, *, order_id: int, user_id: int, questionnaire: str) -> int:
        now = utc_now()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO vip_queue (order_id, user_id, status, questionnaire, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (order_id, user_id, STATUS_IN_QUEUE, questionnaire, now, now),
            )
            return int(cursor.lastrowid)

    def create_buyout_order(
        self,
        *,
        order_id: int,
        user_id: int,
        item_link: str,
        item_price: str,
        comment: str | None,
    ) -> int:
        now = utc_now()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO buyout_orders (
                    order_id, user_id, item_link, item_price, comment, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (order_id, user_id, item_link, item_price, comment, STATUS_AWAITING_PROOF, now, now),
            )
            return int(cursor.lastrowid)

    def update_buyout_status(self, order_id: int, status: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE buyout_orders SET status = ?, updated_at = ? WHERE order_id = ?",
                (status, utc_now(), order_id),
            )

    def create_subscription(
        self,
        *,
        user_id: int,
        order_id: int,
        chat_id: int | None,
        invite_link: str | None,
        days: int = 30,
    ) -> int:
        starts_at = datetime.now(timezone.utc)
        expires_at = starts_at + timedelta(days=days)
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO subscriptions (
                    user_id, order_id, chat_id, invite_link, starts_at, expires_at, status
                )
                VALUES (?, ?, ?, ?, ?, ?, 'active')
                """,
                (user_id, order_id, chat_id, invite_link, starts_at.isoformat(), expires_at.isoformat()),
            )
            return int(cursor.lastrowid)

    def get_subscriptions_for_reminder(self, *, within_days: int = 3) -> list[dict[str, Any]]:
        threshold = datetime.now(timezone.utc) + timedelta(days=within_days)
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM subscriptions
                WHERE status = 'active'
                  AND reminder_sent_at IS NULL
                  AND expires_at <= ?
                ORDER BY expires_at
                """,
                (threshold.isoformat(),),
            ).fetchall()
            return [dict(row) for row in rows]

    def mark_subscription_reminded(self, subscription_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE subscriptions SET reminder_sent_at = ? WHERE id = ?",
                (utc_now(), subscription_id),
            )

    def list_orders(self, *, status: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        query = "SELECT * FROM orders"
        params: list[Any] = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def list_queue_orders(self, *, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM orders
                WHERE status IN (?, ?)
                ORDER BY id DESC
                LIMIT ?
                """,
                (STATUS_IN_QUEUE, STATUS_PROCESSING, limit),
            ).fetchall()
            return [dict(row) for row in rows]

    def list_vip_users(self, *, limit: int = 30) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM users
                WHERE is_vip = 1
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def list_user_ids(self) -> list[int]:
        with self._connect() as conn:
            rows = conn.execute("SELECT telegram_user_id FROM users ORDER BY telegram_user_id").fetchall()
            return [int(row["telegram_user_id"]) for row in rows]

    def get_buyout_order(self, order_id: int) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM buyout_orders WHERE order_id = ?",
                (order_id,),
            ).fetchone()
            return dict(row) if row else None

    def export_order_metadata(self, order_id: int) -> str:
        payload = {
            "order": self.get_order(order_id),
            "payment_proof": self.get_latest_payment_proof(order_id),
            "buyout": self.get_buyout_order(order_id),
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def _ensure_column(self, conn: sqlite3.Connection, table: str, column: str, column_type: str) -> None:
        columns = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn
