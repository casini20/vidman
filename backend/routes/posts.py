import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile

from database import get_db
from services.tiktok import post_video
try:
    from services.instagram import post_instagram_video
except ImportError:
    post_instagram_video = None

router = APIRouter()
logger = logging.getLogger(__name__)

UPLOADS_DIR = os.getenv("UPLOADS_DIR", "uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)


async def _process_post(post_id: str, video_path: str, caption: str):
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, account_id, username FROM post_accounts WHERE post_id=?",
            (post_id,),
        )
        items = [dict(r) for r in await cursor.fetchall()]
        await db.execute(
            "UPDATE posts SET status='in_progress' WHERE id=?", (post_id,)
        )
        await db.commit()

    success = failed = 0

    for item in items:
        pa_id = item["id"]
        account_id = item["account_id"]
        username = item["username"]

        try:
            async with get_db() as db:
                cursor = await db.execute(
                    "SELECT cookies, platform FROM accounts WHERE id=?", (account_id,)
                )
                row = await cursor.fetchone()
                if not row:
                    raise Exception("Account not found in DB")
                cookies = json.loads(row["cookies"])
                platform = row["platform"] or "tiktok"

            if platform == "instagram" and post_instagram_video:
                await post_instagram_video(cookies, video_path, caption)
            elif platform == "instagram":
                raise Exception("Instagram posting not yet implemented")
            elif platform == "twitter":
                raise Exception("Twitter posting not yet implemented")
            else:
                await post_video(cookies, video_path, caption)

            async with get_db() as db:
                await db.execute(
                    "UPDATE post_accounts SET status='success', posted_at=? WHERE id=?",
                    (datetime.now(timezone.utc).isoformat(), pa_id),
                )
                await db.commit()

            success += 1
            logger.info(f"Posted to @{username}")

        except Exception as exc:
            logger.error(f"Failed posting to @{username}: {exc}")
            async with get_db() as db:
                await db.execute(
                    "UPDATE post_accounts SET status='failed', error_message=? WHERE id=?",
                    (str(exc), pa_id),
                )
                await db.commit()
            failed += 1

        await asyncio.sleep(6)

    final = (
        "completed"
        if failed == 0
        else ("failed" if success == 0 else "partial")
    )

    async with get_db() as db:
        await db.execute(
            "UPDATE posts SET status=?, success_count=?, failed_count=? WHERE id=?",
            (final, success, failed, post_id),
        )
        await db.commit()


@router.post("/")
async def create_post(
    background_tasks: BackgroundTasks,
    caption: str = Form(...),
    video: UploadFile = File(...),
    account_ids: str = Form(...),
):
    try:
        ids: list[str] = json.loads(account_ids)
        if not isinstance(ids, list) or not ids:
            raise ValueError
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(
            status_code=400, detail="account_ids must be a non-empty JSON array"
        )

    post_id = str(uuid.uuid4())
    safe_name = video.filename.replace(" ", "_") if video.filename else "video.mp4"
    video_filename = f"{post_id}_{safe_name}"
    video_path = os.path.join(UPLOADS_DIR, video_filename)

    with open(video_path, "wb") as fh:
        fh.write(await video.read())

    async with get_db() as db:
        for aid in ids:
            cursor = await db.execute(
                "SELECT id FROM accounts WHERE id=?", (aid,)
            )
            if not await cursor.fetchone():
                raise HTTPException(
                    status_code=404, detail=f"Account {aid} not found"
                )

        await db.execute(
            """INSERT INTO posts (id, caption, video_filename, video_path, status, total_accounts)
               VALUES (?,?,?,?,'pending',?)""",
            (post_id, caption, safe_name, video_path, len(ids)),
        )

        for aid in ids:
            cursor = await db.execute(
                "SELECT username FROM accounts WHERE id=?", (aid,)
            )
            row = await cursor.fetchone()
            username = row["username"] if row else aid
            await db.execute(
                """INSERT INTO post_accounts (id, post_id, account_id, username, status)
                   VALUES (?,?,?,?,'pending')""",
                (str(uuid.uuid4()), post_id, aid, username),
            )

        await db.commit()

    background_tasks.add_task(_process_post, post_id, video_path, caption)
    return {"post_id": post_id, "status": "pending", "message": "Posting started"}


@router.get("/")
async def list_posts():
    async with get_db() as db:
        cursor = await db.execute(
            """SELECT id, caption, video_filename, status,
                      total_accounts, success_count, failed_count, created_at
               FROM posts ORDER BY created_at DESC LIMIT 50"""
        )
        return [dict(r) for r in await cursor.fetchall()]


@router.get("/{post_id}")
async def get_post(post_id: str):
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM posts WHERE id=?", (post_id,))
        post = await cursor.fetchone()
        if not post:
            raise HTTPException(status_code=404, detail="Post not found")

        cursor = await db.execute(
            "SELECT * FROM post_accounts WHERE post_id=?", (post_id,)
        )
        accounts = [dict(r) for r in await cursor.fetchall()]

    return {**dict(post), "accounts": accounts}