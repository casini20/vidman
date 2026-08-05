import asyncio
import json
import os
import logging
import re
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


async def get_account_info(cookies: list) -> dict:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(user_agent=USER_AGENT)

        try:
            await context.add_cookies(normalize_cookies(cookies))
            page = await context.new_page()

            await page.goto(
                "https://www.tiktok.com/profile",
                wait_until="domcontentloaded",
                timeout=60000,
            )
            await page.wait_for_timeout(5000)

            username = None

            current_url = page.url
            logger.error(f"Profile redirect URL: {current_url}")
            if "/@" in current_url:
                username = current_url.split("/@")[1].strip("/").split("?")[0]
                logger.error(f"Got username from redirect: {username}")

            if not username:
                await page.goto(
                    "https://www.tiktok.com/",
                    wait_until="domcontentloaded",
                    timeout=60000,
                )
                await page.wait_for_timeout(8000)

                try:
                    link = await page.query_selector('[data-e2e="nav-profile"]')
                    if link:
                        href = await link.get_attribute("href") or ""
                        if "/@" in href:
                            username = href.split("/@")[1].strip("/").split("?")[0]
                except Exception:
                    pass

            if not username:
                try:
                    content = await page.content()
                    match = re.search(r'"webapp\.user-detail".*?"uniqueId":"([^"]+)"', content)
                    if match:
                        username = match.group(1)
                except Exception:
                    pass

            if not username:
                raise Exception(
                    "Could not detect logged-in user — are these valid TikTok cookies?"
                )

            await page.goto(
                f"https://www.tiktok.com/@{username}",
                wait_until="domcontentloaded",
                timeout=60000,
            )
            await page.wait_for_timeout(8000)

            followers = following = likes = "0"
            display_name = username
            avatar_url = ""

            for attr, selector in [
                ("followers", '[data-e2e="followers-count"]'),
                ("following", '[data-e2e="following-count"]'),
                ("likes", '[data-e2e="likes-count"]'),
            ]:
                try:
                    el = await page.query_selector(selector)
                    if el:
                        val = await el.inner_text()
                        if attr == "followers":
                            followers = val
                        elif attr == "following":
                            following = val
                        else:
                            likes = val
                except Exception:
                    pass

            try:
                el = await page.query_selector('[data-e2e="user-title"]')
                if el:
                    display_name = await el.inner_text()
            except Exception:
                pass

            try:
                el = await page.query_selector('[data-e2e="user-avatar"] img')
                if el:
                    avatar_url = await el.get_attribute("src") or ""
            except Exception:
                pass

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