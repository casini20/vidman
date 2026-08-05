import asyncio
import json
import os
import logging
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"

SAMESITE_MAP = {
    "no_restriction": "None",
    "lax": "Lax",
    "strict": "Strict",
    "unspecified": "None",
}

def normalize_cookies(cookies: list) -> list:
    result = []
    for c in cookies:
        cookie = dict(c)
        raw = (cookie.get("sameSite") or "").lower()
        cookie["sameSite"] = SAMESITE_MAP.get(raw, "None")
        for key in ["hostOnly", "session", "storeId", "id"]:
            cookie.pop(key, None)
        if not cookie.get("path"):
            cookie["path"] = "/"
        if not cookie.get("domain"):
            cookie["url"] = "https://www.tiktok.com"
        if not cookie.get("expirationDate"):
            cookie.pop("expirationDate", None)
        result.append(cookie)
    return result

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def _format_count(n: int) -> str:
    """Format a raw integer count the same way TikTok displays it (e.g. 1200 → '1.2K')."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


async def get_account_info(cookies: list) -> dict:
    """Retrieve the logged-in user's profile by intercepting the API call
    that TikTok's own page makes on load, rather than issuing a manual fetch.

    Strategy
    --------
    1. Register a Playwright response handler BEFORE navigating, so it
       catches every network response the page fires.
    2. Navigate to https://www.tiktok.com/ — TikTok's own JS fires
       user-info requests with all the correct signed params and cookies.
    3. Capture and parse the first matching response body.
       No manual request-signing, no CORS issues, no empty-body problems.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(user_agent=USER_AGENT)

        try:
            await context.add_cookies(normalize_cookies(cookies))
            page = await context.new_page()

            captured: dict = {}

            async def handle_response(response):
                if captured:
                    return
                url = response.url
                if "tiktok.com/api" in url or "tiktok.com/passport" in url:
                    logger.info(f"TikTok API call: {url}")
                if (
                    "/api/user/detail/" in url
                    or "passport/account/info" in url
                    or "/passport/user/user_info" in url
                    or "/api/recommend/user/" in url
                    or "user/profile/self" in url
                    or "/api/user/info/" in url
                ):
                    try:
                        body = await response.text()
                        if body and body.strip().startswith("{"):
                            data = json.loads(body)
                            if (
                                data.get("userInfo")
                                or data.get("data", {}).get("user_info")
                                or data.get("data", {}).get("userInfo")
                            ):
                                captured["data"] = data
                                captured["url"] = url
                                logger.debug(f"Captured user API response from: {url}")
                    except Exception as e:
                        logger.debug(f"Response handler error for {url}: {e}")

            page.on("response", handle_response)

            await page.goto(
                "https://www.tiktok.com/",
                wait_until="domcontentloaded",
                timeout=60000,
            )

            # Give TikTok's JS up to 10 s to fire its user-info call
            for _ in range(20):
                if captured:
                    break
                await page.wait_for_timeout(500)

            if not captured:
                raise Exception(
                    "Could not intercept TikTok user-info API call — "
                    "are these valid / non-expired TikTok cookies?"
                )

            api_result = captured["data"]
            logger.debug(f"TikTok intercepted response keys: {list(api_result.keys())}")

            # Normalise across the two known response shapes:
            #   Shape A  (tiktok.com homepage): { userInfo: { user: {}, stats: {} } }
            #   Shape B  (passport endpoints):  { data: { user_info: {} } }
            user_info = (
                api_result.get("userInfo")
                or api_result.get("data", {}).get("userInfo")
                or {}
            )
            passport_info = api_result.get("data", {}).get("user_info") or {}

            if user_info:
                user         = user_info.get("user") or {}
                stats        = user_info.get("stats") or {}
                username     = user.get("uniqueId") or user.get("nickname") or ""
                display_name = user.get("nickname") or username
                avatar_url   = user.get("avatarLarger") or user.get("avatarMedium") or ""
                followers    = _format_count(int(stats.get("followerCount", 0)))
                following    = _format_count(int(stats.get("followingCount", 0)))
                likes        = _format_count(int(stats.get("heartCount", stats.get("diggCount", 0))))
            elif passport_info:
                username     = passport_info.get("unique_id") or passport_info.get("nickname") or ""
                display_name = passport_info.get("nickname") or username
                avatar_url   = passport_info.get("avatar_larger", {}).get("url_list", [""])[0]
                followers    = _format_count(int(passport_info.get("follower_count", 0)))
                following    = _format_count(int(passport_info.get("following_count", 0)))
                likes        = _format_count(int(passport_info.get("total_favorited", 0)))
            else:
                raise Exception(
                    "Intercepted an API response but could not find user data inside it."
                )

            if not username:
                raise Exception(
                    "Could not parse username from intercepted TikTok response — "
                    "are these valid TikTok cookies?"
                )

            logger.info(f"TikTok intercepted: detected user @{username}")

            return {
                "username": username,
                "display_name": display_name,
                "avatar_url": avatar_url,
                "followers": followers,
                "following": following,
                "likes": likes,
            }

        finally:
            await browser.close()


async def post_video(cookies: list, video_path: str, caption: str) -> dict:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(user_agent=USER_AGENT)

        try:
            await context.add_cookies(normalize_cookies(cookies))
            page = await context.new_page()

            await page.goto(
                "https://www.tiktok.com/upload",
                wait_until="domcontentloaded",
                timeout=60000,
            )
            await page.wait_for_timeout(8000)

            for btn_text in ["Accept all", "Accept All", "Accept", "Decline optional"]:
                try:
                    btn = page.get_by_role("button", name=btn_text)
                    if await btn.is_visible(timeout=2000):
                        await btn.click()
                        await page.wait_for_timeout(1000)
                        break
                except Exception:
                    pass

            iframe_locator = page.frame_locator("iframe").first
            file_input = iframe_locator.locator('input[type="file"]')
            await file_input.wait_for(timeout=15000)
            await file_input.set_input_files(video_path)
            logger.info("Video file set — waiting for processing...")

            await page.wait_for_timeout(10000)

            caption_selectors = [
                '.public-DraftEditor-content',
                '[contenteditable="true"]',
                '[data-e2e="video-desc-input"]',
                '.notranslate[contenteditable]',
            ]
            caption_added = False
            for sel in caption_selectors:
                try:
                    el = iframe_locator.locator(sel).first
                    if await el.is_visible(timeout=4000):
                        await el.click()
                        await el.press("Control+a")
                        await el.type(caption, delay=30)
                        caption_added = True
                        break
                except Exception:
                    pass

            await page.wait_for_timeout(1000)

            post_selectors = [
                'button[data-e2e="post-btn"]',
                'button:has-text("Post")',
                '[class*="post-btn"]',
                'button.btn-post',
            ]
            posted = False
            for sel in post_selectors:
                try:
                    btn = iframe_locator.locator(sel).first
                    if await btn.is_enabled(timeout=5000):
                        await btn.click()
                        posted = True
                        break
                except Exception:
                    pass

            if not posted:
                raise Exception("Could not find or click the Post button")

            await page.wait_for_timeout(6000)
            return {"success": True}

        except Exception as e:
            logger.error(f"post_video error: {e}")
            raise
        finally:
            await browser.close()