import logging
import json

logger = logging.getLogger(__name__)


def get_cookie_value(cookies: list, name: str) -> str:
    for c in cookies:
        if c.get("name") == name:
            return c.get("value", "")
    return ""


async def get_instagram_account_info(cookies: list) -> dict:
    session_id = get_cookie_value(cookies, "sessionid")
    if not session_id:
        raise Exception("No sessionid cookie found - please re-export your Instagram cookies")

    try:
        from ensta import WebSession
        # session_data format ensta expects is just the sessionid value
        ws = WebSession(session_data=session_id)

        # get_username returns the logged-in username
        username = ws.get_username()
        if not username:
            raise Exception("Could not get username from session")

        profile = ws.profile(username)
        logger.info(f"Instagram profile fetched: {username}")

        return {
            "username": username,
            "display_name": getattr(profile, "full_name", None) or username,
            "avatar_url": getattr(profile, "profile_picture_url", "") or "",
            "followers": str(getattr(profile, "follower_count", 0)),
            "following": str(getattr(profile, "following_count", 0)),
            "likes": "0",
            "views": str(getattr(profile, "media_count", 0)),
        }
    except Exception as e:
        logger.error(f"Instagram ensta error: {e}", exc_info=True)
        raise Exception(f"Could not verify Instagram session: {e}")