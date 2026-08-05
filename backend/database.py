import aiosqlite
import os

DB_PATH = os.getenv("DB_PATH", "tiktok_manager.db")

async def get_db():
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    return db

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                display_name TEXT,
                avatar_url TEXT,
                cookies TEXT NOT NULL,
                followers TEXT DEFAULT '0',
                following TEXT DEFAULT '0',
                likes TEXT DEFAULT '0',
                last_synced TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                id TEXT PRIMARY KEY,
                caption TEXT NOT NULL,
                video_filename TEXT,
                video_path TEXT,
                status TEXT DEFAULT 'pending',
                total_accounts INTEGER DEFAULT 0,
                success_count INTEGER DEFAULT 0,
                failed_count INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS post_accounts (
                id TEXT PRIMARY KEY,
                post_id TEXT NOT NULL,
                account_id TEXT NOT NULL,
                username TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                error_message TEXT,
                posted_at TEXT,
                FOREIGN KEY (post_id) REFERENCES posts(id),
                FOREIGN KEY (account_id) REFERENCES accounts(id)
            )
        """)
        await db.commit()
