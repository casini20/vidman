import asyncio
import json
import os
import logging
import re
import httpx

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

def cookies_to_header(cookies: list) -> str:
    return "; ".join(f"{c['name']}={c['value']}" for c in cookies if c.get("name") and c.get("value"))

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


async def get_account_info(cookies: list) -> dict:
    cookie_header = cookies_to_header(cookies)
    headers = {
        "User-Agent": USER_AGENT,
        "Cookie": cookie_header,
        "Referer": "https://www.tiktok.com/",
    }

    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.get(
            "https://www.tiktok.com/passport/web/account/info/",
            headers=headers,
            timeout=30,
        )
        logger.error(f"Passport API status: {resp.status_code}")
        logger.error(f"Passport API response: {resp.text[:500]}")

        try:
            data = resp.json()
            user_data = data.get("data", {})
            username = user_data.get("username") or user_data.get("unique_id")
            display_name = user_data.get("nickname", username)
            avatar_url = user_data.get("avatar_url", "")

            if username:
                return {
                    "username": username,
                    "display_name": display_name or username,
                    "avatar_url": avatar_url,
                    "followers": "0",
                    "following": "0",
                    "likes": "0",
                }
        except Exception as e:
            logger.error(f"Failed to parse passport API: {e}")

    raise Exception("Could not verify TikTok session — please re-export your cookies and try again")


async def post_video(cookies: list, video_path: str, caption: str) -> dict:
    from playwright.async_api import async_playwright

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

            await page.wait_for_timeout(10000)

            caption_selectors = [
                '.public-DraftEditor-content',
                '[contenteditable="true"]',
                '[data-e2e="video-desc-input"]',
                '.notranslate[contenteditable]',
            ]
            for sel in caption_selectors:
                try:
                    el = iframe_locator.locator(sel).first
                    if await el.is_visible(timeout=4000):
                        await el.click()
                        await el.press("Control+a")
                        await el.type(caption, delay=30)
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