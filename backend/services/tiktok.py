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
    """Retrieve the logged-in user's profile by calling TikTok's internal
    user-info API endpoint instead of scraping DOM elements.

    Strategy
    --------
    1. Load https://www.tiktok.com/ in a Playwright page so that all
       cookies (including the anti-bot ``msToken`` / ``tt_chain_token``)
       are attached to the browser context.
    2. Use ``page.evaluate`` to call ``fetch`` *from inside the page*,
       which means the request carries every cookie and the same
       ``Origin``/``Referer`` headers that a real browser would send.
       This avoids having to replicate TikTok's request-signing logic in
       Python.
    3. Parse the JSON response — no HTML scraping required.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(user_agent=USER_AGENT)

        try:
            await context.add_cookies(normalize_cookies(cookies))
            page = await context.new_page()

            # Navigate to TikTok so cookies are active and the page
            # origin matches what the API expects.
            await page.goto(
                "https://www.tiktok.com/",
                wait_until="domcontentloaded",
                timeout=60000,
            )
            await page.wait_for_timeout(3000)

            # Call TikTok's internal "self" user-info endpoint from
            # inside the page context so all cookies/headers are sent
            # automatically.
            api_result = await page.evaluate(
                """async () => {
                    const params = new URLSearchParams({
                        aid: '1988',
                        app_language: 'en',
                        app_name: 'tiktok_web',
                        browser_language: navigator.language || 'en-US',
                        browser_name: 'Mozilla',
                        browser_online: 'true',
                        browser_platform: 'Win32',
                        browser_version: navigator.userAgent,
                        channel: 'tiktok_web',
                        cookie_enabled: 'true',
                        device_platform: 'web_pc',
                        focus_state: 'true',
                        from_page: 'user',
                        history_len: String(history.length),
                        is_fullscreen: 'false',
                        is_page_visible: 'true',
                        os: 'windows',
                        priority_region: '',
                        referer: '',
                        region: 'US',
                        screen_height: String(screen.height),
                        screen_width: String(screen.width),
                        tz_name: Intl.DateTimeFormat().resolvedOptions().timeZone,
                        webcast_language: 'en',
                    });

                    const url =
                        'https://www.tiktok.com/api/user/detail/?' + params.toString();

                    const resp = await fetch(url, {
                        method: 'GET',
                        credentials: 'include',
                        headers: {
                            'Accept': 'application/json, text/plain, */*',
                            'Referer': 'https://www.tiktok.com/',
                        },
                    });

                    if (!resp.ok) {
                        return { error: `HTTP ${resp.status}` };
                    }
                    return await resp.json();
                }"""
            )

            logger.debug(f"TikTok API raw response keys: {list(api_result.keys())}")

            # statusCode 0 means success; anything else is an auth/API error.
            status_code = api_result.get("statusCode", api_result.get("status_code", -1))
            if status_code != 0:
                raise Exception(
                    f"TikTok API returned statusCode={status_code} — "
                    "are these valid / non-expired TikTok cookies?"
                )

            user = (api_result.get("userInfo") or api_result.get("user") or {})
            # The response nests data under userInfo.user and userInfo.stats
            if "user" in user:
                stats = user.get("stats", {})
                user = user["user"]
            else:
                stats = api_result.get("userInfo", {}).get("stats", {})

            username = user.get("uniqueId") or user.get("nickname") or ""
            display_name = user.get("nickname") or username
            avatar_url = user.get("avatarLarger") or user.get("avatarMedium") or ""

            followers = _format_count(int(stats.get("followerCount", 0)))
            following = _format_count(int(stats.get("followingCount", 0)))
            likes = _format_count(int(stats.get("heartCount", stats.get("diggCount", 0))))

            if not username:
                raise Exception(
                    "Could not parse username from TikTok API response — "
                    "are these valid TikTok cookies?"
                )

            logger.info(f"TikTok API: detected user @{username}")

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