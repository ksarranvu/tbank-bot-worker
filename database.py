import aiosqlite
from datetime import datetime

DB_NAME = "blackcard.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS employees (
                user_id INTEGER PRIMARY KEY,
                full_name TEXT,
                username TEXT,
                created_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER,
                referred_user_id INTEGER UNIQUE,
                referred_username TEXT,
                referred_full_name TEXT,
                created_at TEXT,
                status TEXT DEFAULT 'clicked',
                FOREIGN KEY (employee_id) REFERENCES employees (user_id)
            )
        """)
        await db.commit()

async def add_employee(user_id: int, full_name: str, username: str = None):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT OR IGNORE INTO employees (user_id, full_name, username, created_at) VALUES (?, ?, ?, ?)",
            (user_id, full_name, username, datetime.now().isoformat())
        )
        await db.commit()

async def get_employee_stats(employee_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT status, COUNT(*) FROM referrals WHERE employee_id = ? GROUP BY status",
            (employee_id,)
        )
        rows = await cursor.fetchall()
        stats = {"clicked": 0, "applied": 0, "completed": 0}
        for status, count in rows:
            stats[status] = count
        return stats

async def get_all_stats():
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("""
            SELECT e.user_id, e.full_name, e.username,
                   SUM(CASE WHEN r.status = 'clicked' THEN 1 ELSE 0 END) as clicked,
                   SUM(CASE WHEN r.status = 'applied' THEN 1 ELSE 0 END) as applied,
                   SUM(CASE WHEN r.status = 'completed' THEN 1 ELSE 0 END) as completed
            FROM employees e
            LEFT JOIN referrals r ON e.user_id = r.employee_id
            GROUP BY e.user_id
            ORDER BY completed DESC, applied DESC
        """)
        return await cursor.fetchall()

async def add_referral(employee_id: int, referred_user_id: int, username: str, full_name: str) -> bool:
    """Возвращает True, если запись новая"""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT id FROM referrals WHERE referred_user_id = ?",
            (referred_user_id,)
        )
        exists = await cursor.fetchone()
        if exists:
            return False

        await db.execute(
            """INSERT INTO referrals 
               (employee_id, referred_user_id, referred_username, referred_full_name, created_at) 
               VALUES (?, ?, ?, ?, ?)""",
            (employee_id, referred_user_id, username, full_name, datetime.now().isoformat())
        )
        await db.commit()
        return True

async def update_referral_status(referred_user_id: int, status: str) -> dict | None:
    """Обновляет статус и возвращает данные о реферале"""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            """SELECT employee_id, referred_full_name, referred_username, status 
               FROM referrals WHERE referred_user_id = ?""",
            (referred_user_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None

        old_status = row[3]
        if old_status == status:
            return None

        await db.execute(
            "UPDATE referrals SET status = ? WHERE referred_user_id = ?",
            (status, referred_user_id)
        )
        await db.commit()

        return {
            "employee_id": row[0],
            "referred_full_name": row[1],
            "referred_username": row[2],
            "old_status": old_status,
            "new_status": status
        }

async def get_employee_name(employee_id: int) -> str:
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            "SELECT full_name, username FROM employees WHERE user_id = ?",
            (employee_id,)
        )
        row = await cursor.fetchone()
        if row:
            name = row[0] or "Без имени"
            username = f" (@{row[1]})" if row[1] else ""
            return f"{name}{username}"
        return f"ID {employee_id}"
