from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import json
import uuid
from datetime import datetime, timezone
from database import get_db
from services.tiktok import get_account_info

router = APIRouter()


class AddAccountRequest(BaseModel):
    cookies: str  # JSON array exported from Cookie-Editor


def row_to_dict(row) -> dict:
    return dict(row)


@router.get("/")
async def list_accounts():
    async with await get_db() as db:
        cursor = await db.execute(
            "SELECT id, username, display_name, avatar_url, "
            "followers, following, likes, last_synced, created_at FROM accounts"
        )
        rows = await cursor.fetchall()
        return [row_to_dict(r) for r in rows]


@router.post("/")
async def add_account(request: AddAccountRequest):
    # Parse & validate cookie JSON
    try:
        cookies = json.loads(request.cookies)
        if not isinstance(cookies, list):
            raise ValueError("Expected a JSON array of cookies")
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid cookies JSON: {exc}")

    # Verify the session is still alive and grab profile info
    try:
        info = await get_account_info(cookies)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Could not verify TikTok session: {exc}",
        )

    now = datetime.now(timezone.utc).isoformat()
    cookies_str = json.dumps(cookies)

    async with await get_db() as db:
        cursor = await db.execute(
            "SELECT id FROM accounts WHERE username = ?", (info["username"],)
        )
        existing = await cursor.fetchone()

        if existing:
            await db.execute(
                """UPDATE accounts
                   SET cookies=?, display_name=?, avatar_url=?,
                       followers=?, following=?, likes=?, last_synced=?
                   WHERE username=?""",
                (
                    cookies_str,
                    info["display_name"],
                    info["avatar_url"],
                    info["followers"],
                    info["following"],
                    info["likes"],
                    now,
                    info["username"],
                ),
            )
            await db.commit()
            return {"message": "Account refreshed", **info}

        account_id = str(uuid.uuid4())
        await db.execute(
            """INSERT INTO accounts
               (id, username, display_name, avatar_url, cookies, followers, following, likes, last_synced)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                account_id,
                info["username"],
                info["display_name"],
                info["avatar_url"],
                cookies_str,
                info["followers"],
                info["following"],
                info["likes"],
                now,
            ),
        )
        await db.commit()

    return {"message": "Account connected", "account_id": account_id, **info}


@router.delete("/{account_id}")
async def remove_account(account_id: str):
    async with await get_db() as db:
        cursor = await db.execute(
            "SELECT id FROM accounts WHERE id=?", (account_id,)
        )
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Account not found")
        await db.execute("DELETE FROM accounts WHERE id=?", (account_id,))
        await db.commit()
    return {"message": "Account removed"}


@router.post("/{account_id}/sync")
async def sync_stats(account_id: str):
    async with await get_db() as db:
        cursor = await db.execute(
            "SELECT cookies FROM accounts WHERE id=?", (account_id,)
        )
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Account not found")
        cookies = json.loads(row["cookies"])

    try:
        info = await get_account_info(cookies)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Sync failed: {exc}")

    now = datetime.now(timezone.utc).isoformat()
    async with await get_db() as db:
        await db.execute(
            """UPDATE accounts
               SET followers=?, following=?, likes=?, display_name=?, avatar_url=?, last_synced=?
               WHERE id=?""",
            (
                info["followers"],
                info["following"],
                info["likes"],
                info["display_name"],
                info["avatar_url"],
                now,
                account_id,
            ),
        )
        await db.commit()

    return {"message": "Stats synced", **info}
