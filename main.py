import os
import asyncio
import aiosqlite
from fastmcp import FastMCP

DB_PATH = os.path.join(os.path.dirname(__file__), "expenses.db")
CATEGORIES_PATH = os.path.join(os.path.dirname(__file__), "categories.json")

mcp = FastMCP(name="expense-tracker")

_db_ready = False
_db_lock = asyncio.Lock()


async def init_db():
    async with aiosqlite.connect(DB_PATH, timeout=30) as conn:
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS expenses(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                subcategory TEXT DEFAULT '',
                note TEXT DEFAULT ''
            )
        """)
        await conn.commit()


async def ensure_db():
    global _db_ready
    if _db_ready:
        return
    async with _db_lock:
        if not _db_ready:
            await init_db()
            _db_ready = True


@mcp.tool()
async def add_expense(
    category: str,
    date: str,
    amount: float,
    subcategory: str = "",
    note: str = "",
):
    '''Add a new expense entry to the database.'''
    await ensure_db()
    async with aiosqlite.connect(DB_PATH, timeout=30) as conn:
        cur = await conn.execute(
            "INSERT INTO expenses(date, amount, category, subcategory, note) VALUES (?,?,?,?,?)",
            (date, amount, category, subcategory, note),
        )
        await conn.commit()
        return {"status": "ok", "id": cur.lastrowid}


@mcp.tool()
async def list_expenses(start_date: str, end_date: str):
    '''List expense entries within an inclusive date range.'''
    await ensure_db()
    async with aiosqlite.connect(DB_PATH, timeout=30) as conn:
        cur = await conn.execute(
            """
            SELECT id, date, amount, category, subcategory, note
            FROM expenses
            WHERE date BETWEEN ? AND ?
            ORDER BY id ASC
            """,
            (start_date, end_date),
        )
        cols = [d[0] for d in cur.description]
        rows = await cur.fetchall()
        return [dict(zip(cols, r)) for r in rows]


@mcp.tool()
async def summarize(start_date: str, end_date: str, category: str | None = None):
    '''Summarizes expenses within a date range, optionally for one category.'''
    await ensure_db()
    query = """
        SELECT category, SUM(amount) AS total_amount
        FROM expenses
        WHERE date BETWEEN ? AND ?
    """
    params = [start_date, end_date]

    if category:
        query += " AND category = ?"
        params.append(category)

    query += " GROUP BY category ORDER BY category ASC"

    async with aiosqlite.connect(DB_PATH, timeout=30) as conn:
        cur = await conn.execute(query, params)
        cols = [d[0] for d in cur.description]
        rows = await cur.fetchall()
        return [dict(zip(cols, r)) for r in rows]


def _read_categories() -> str:
    with open(CATEGORIES_PATH, "r", encoding="utf-8") as f:
        return f.read()


@mcp.resource("expense://categories", mime_type="application/json")
async def categories():
    return await asyncio.to_thread(_read_categories)


if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000)
