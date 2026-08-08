import logging
import httpx

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

def cookies_to_header(cookies: list) -> str:
    return "; ".join(f"{c['name']}={c['value']}" for c in cookies if c.get("name") and c.get("value"))

def get_cookie_value(cookies: list, name: str) -> str:
    for c in cookies:
        if c.get("name") == name:
            return c.get("value", "")
    return ""


async def get_instagram_account_info(cookies: list) -> dict:
    cookie_header = cookies_to_header(cookies)
    csrf_token = get_cookie_value(cookies, "csrftoken")
    user_id = get_cookie_value(cookies, "ds_user_id")

    headers = {
        "User-Agent": USER_AGENT,
        "Cookie": cookie_header,
        "X-CSRFToken": csrf_token,
        "X-IG-App-ID": "936619743392459",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://www.instagram.com/",
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(follow_redirects=True) as client:
        # Get user info by user_id
        if user_id:
            try:
                resp = await client.get(
                    f"https://i.instagram.com/api/v1/users/{user_id}/info/",
                    headers=headers,
                    timeout=20,
                )
                logger.warning(f"Instagram user info status: {resp.status_code} body: {resp.text[:300]}")
                data = resp.json()
                user = data.get("user", {})
                if user.get("username"):
                    return _parse_user(user)
            except Exception as e:
                logger.warning(f"Instagram user info by id failed: {e}")

        # Fallback: current user endpoint
        try:
            resp = await client.get(
                "https://www.instagram.com/api/v1/accounts/current_user/?edit=true",
                headers=headers,
                timeout=20,
            )
            logger.warning(f"Instagram current_user status: {resp.status_code} body: {resp.text[:300]}")
            data = resp.json()
            user = data.get("user", {})
            if user.get("username"):
                return _parse_user(user)
        except Exception as e:
            logger.warning(f"Instagram current_user endpoint failed: {e}")

    raise Exception("Could not verify Instagram session - please re-export your cookies and try again")


def _parse_user(user: dict) -> dict:
    username = user.get("username", "")
    display_name = user.get("full_name") or username
    avatar_url = user.get("profile_pic_url", "")
    followers = str(user.get("follower_count", user.get("edge_followed_by", {}).get("count", 0)))
    following = str(user.get("following_count", user.get("edge_follow", {}).get("count", 0)))
    likes = "0"
    views = str(user.get("media_count", 0))
    return {
        "username": username,
        "display_name": display_name,
        "avatar_url": avatar_url,
        "followers": followers,
        "following": following,
        "likes": likes,
        "views": views,
    }