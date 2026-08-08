import logging
from urllib.parse import unquote

logger = logging.getLogger(__name__)


def get_cookie_value(cookies: list, name: str) -> str:
    for c in cookies:
        if c.get("name") == name:
            return c.get("value", "")
    return ""


async def get_instagram_account_info(cookies: list) -> dict:
    session_id = get_cookie_value(cookies, "sessionid")
    ds_user_id = get_cookie_value(cookies, "ds_user_id")

    if not session_id:
        raise Exception("No sessionid cookie found — please re-export your Instagram cookies")

    # Extract user_id from ds_user_id or from sessionid prefix
    user_id = ds_user_id
    if not user_id and session_id:
        # sessionid format: "46940659139%3Axxx" — user_id is before the first %3A
        decoded = unquote(session_id)
        user_id = decoded.split(":")[0]

    if not user_id:
        raise Exception("Could not extract user ID from cookies")

    # Use user_id as username placeholder — will be shown as @{user_id} until synced
    logger.info(f"Instagram session accepted for user_id={user_id}")
    return {
        "username": f"ig_{user_id}",
        "display_name": f"Instagram {user_id}",
        "avatar_url": "",
        "followers": "0",
        "following": "0",
        "likes": "0",
        "views": "0",
    }