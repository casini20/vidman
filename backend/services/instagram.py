import logging
import httpx

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def get_cookie_value(cookies: list, name: str) -> str:
    for c in cookies:
        if c.get("name") == name:
            return c.get("value", "")
    return ""


def cookies_to_header(cookies: list) -> str:
    return "; ".join(f"{c['name']}={c['value']}" for c in cookies if c.get("name") and c.get("value"))


async def get_instagram_account_info(cookies: list) -> dict:
    session_id = get_cookie_value(cookies, "sessionid")
    csrf_token = get_cookie_value(cookies, "csrftoken")
    ds_user_id = get_cookie_value(cookies, "ds_user_id")

    if not session_id:
        raise Exception("No sessionid cookie found - please re-export your Instagram cookies")

    cookie_header = cookies_to_header(cookies)

    # Try multiple endpoints with different header combos
    endpoints = [
        {
            "url": f"https://i.instagram.com/api/v1/users/{ds_user_id}/info/",
            "headers": {
                "User-Agent": "Instagram 275.0.0.27.98 Android (33/13; 420dpi; 1080x2400; samsung; SM-G991B; o1s; exynos2100; en_US; 458229258)",
                "Cookie": cookie_header,
                "X-CSRFToken": csrf_token,
                "X-IG-App-ID": "567067343352427",
                "Accept": "*/*",
            },
        },
        {
            "url": "https://i.instagram.com/api/v1/accounts/current_user/?edit=true",
            "headers": {
                "User-Agent": "Instagram 275.0.0.27.98 Android (33/13; 420dpi; 1080x2400; samsung; SM-G991B; o1s; exynos2100; en_US; 458229258)",
                "Cookie": cookie_header,
                "X-CSRFToken": csrf_token,
                "X-IG-App-ID": "567067343352427",
                "Accept": "*/*",
            },
        },
    ]

    async with httpx.AsyncClient(follow_redirects=True) as client:
        for ep in endpoints:
            try:
                resp = await client.get(ep["url"], headers=ep["headers"], timeout=20)
                logger.warning(f"Instagram {ep['url']} → {resp.status_code}: {resp.text[:300]}")
                data = resp.json()
                user = data.get("user", {})
                if user.get("username"):
                    return {
                        "username": user["username"],
                        "display_name": user.get("full_name") or user["username"],
                        "avatar_url": user.get("profile_pic_url", ""),
                        "followers": str(user.get("follower_count", 0)),
                        "following": str(user.get("following_count", 0)),
                        "likes": "0",
                        "views": str(user.get("media_count", 0)),
                    }
            except Exception as e:
                logger.warning(f"Instagram endpoint {ep['url']} failed: {e}")

    raise Exception("Could not verify Instagram session - please re-export your cookies and try again")