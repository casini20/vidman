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
        browser = await p.chromium.launch(
            headless=HEADLESS,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ]
        )
        context = await browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 800},
        )
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)

        try:
            await context.add_cookies(normalize_cookies(cookies))
            page = await context.new_page()

            # Try the upload page
            await page.goto(
                "https://www.tiktok.com/upload",
                wait_until="networkidle",
                timeout=60000,
            )
            await page.wait_for_timeout(5000)
            logger.info(f"Upload page URL: {page.url}")
            logger.info(f"Upload page title: {await page.title()}")

            # Take screenshot for debugging
            await page.screenshot(path="upload_page.png")
            logger.info("Screenshot saved to upload_page.png")

            # Log all frames
            frames = page.frames
            logger.info(f"Number of frames: {len(frames)}")
            for i, frame in enumerate(frames):
                logger.info(f"Frame {i}: {frame.url}")

            # Try finding file input anywhere on the page
            file_input = page.locator('input[type="file"]')
            count = await file_input.count()
            logger.info(f"File inputs found directly: {count}")

            if count > 0:
                await file_input.first.set_input_files(video_path)
                logger.info("File set via direct input!")
            else:
                # Try each frame
                for i, frame in enumerate(frames):
                    try:
                        inputs = await frame.query_selector_all('input[type="file"]')
                        logger.info(f"Frame {i} has {len(inputs)} file inputs")
                        if inputs:
                            await inputs[0].set_input_files(video_path)
                            logger.info(f"File set via frame {i}!")
                            break
                    except Exception as e:
                        logger.info(f"Frame {i} error: {e}")
                else:
                    raise Exception("Could not find file input on any frame")

            await page.wait_for_timeout(15000)

            # Caption
            caption_selectors = [
                '.public-DraftEditor-content',
                '[contenteditable="true"]',
                '[data-e2e="video-desc-input"]',
                '.notranslate[contenteditable]',
            ]
            for sel in caption_selectors:
                for frame in [page] + list(page.frames):
                    try:
                        el = frame.locator(sel).first if hasattr(frame, 'locator') else None
                        if el and await el.is_visible(timeout=2000):
                            await el.click()
                            await el.press("Control+a")
                            await el.type(caption, delay=30)
                            logger.info(f"Caption added via {sel}")
                            break
                    except Exception:
                        pass

            await page.wait_for_timeout(1000)

            # Post button
            post_selectors = [
                'button[data-e2e="post-btn"]',
                'button:has-text("Post")',
                '[class*="post-btn"]',
            ]
            posted = False
            for sel in post_selectors:
                for frame in [page] + list(page.frames):
                    try:
                        btn = frame.locator(sel).first if hasattr(frame, 'locator') else None
                        if btn and await btn.is_enabled(timeout=2000):
                            await btn.click()
                            posted = True
                            logger.info(f"Posted via {sel}")
                            break
                    except Exception:
                        pass
                if posted:
                    break

            if not posted:
                raise Exception("Could not find or click the Post button")

            await page.wait_for_timeout(6000)
            return {"success": True}

        except Exception as e:
            logger.error(f"post_video error: {e}")
            raise
        finally:
            await browser.close()