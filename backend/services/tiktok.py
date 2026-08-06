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

    raise Exception("Could not verify TikTok session - please re-export your cookies and try again")


async def dismiss_popups(page):
    """Dismiss any visible popups."""
    for btn_text in ["Got it", "Turn on", "Skip", "Close"]:
        try:
            btn = page.get_by_role("button", name=btn_text)
            if await btn.is_visible(timeout=500):
                await btn.click()
                logger.info(f"Dismissed popup: {btn_text}")
                await page.wait_for_timeout(500)
        except Exception:
            pass


async def click_post_button(page) -> bool:
    """Try to click the Post/Plaatsen button."""
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await page.wait_for_timeout(1000)
    post_selectors = [
        'button:has-text("Plaatsen")',
        'button:has-text("Post")',
        'button[data-e2e="post-btn"]',
        '[class*="post-btn"]',
        'div[class*="btn-post"]',
    ]
    for sel in post_selectors:
        for frame in [page] + list(page.frames):
            try:
                btn = frame.locator(sel).first if hasattr(frame, 'locator') else None
                if btn and await btn.is_enabled(timeout=2000):
                    await btn.click()
                    logger.info(f"Clicked post button via {sel}")
                    return True
            except Exception:
                pass
    return False


async def handle_post_confirmation(page):
    """Handle the 'Post now' confirmation popup."""
    await page.wait_for_timeout(2000)
    for btn_text in ["Nu plaatsen", "Post now", "Confirm", "Continue"]:
        try:
            btn = page.get_by_role("button", name=btn_text)
            if await btn.is_visible(timeout=3000):
                await btn.click()
                logger.info(f"Clicked confirmation: {btn_text}")
                return
        except Exception:
            pass


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

            await page.goto(
                "https://www.tiktok.com/upload",
                wait_until="domcontentloaded",
                timeout=60000,
            )
            await page.wait_for_timeout(5000)
            logger.info(f"Upload page URL: {page.url}")

            await page.screenshot(path="upload_page.png")

            frames = page.frames
            file_input = page.locator('input[type="file"]')
            count = await file_input.count()

            if count > 0:
                await file_input.first.set_input_files(video_path)
                logger.info("File set via direct input!")
            else:
                for i, frame in enumerate(frames):
                    try:
                        inputs = await frame.query_selector_all('input[type="file"]')
                        if inputs:
                            await inputs[0].set_input_files(video_path)
                            logger.info(f"File set via frame {i}!")
                            break
                    except Exception as e:
                        logger.info(f"Frame {i} error: {e}")
                else:
                    raise Exception("Could not find file input on any frame")

            await page.wait_for_timeout(30000)
            await page.screenshot(path="after_upload.png")

            # Dismiss any popups that appeared during upload
            await dismiss_popups(page)
            await page.wait_for_timeout(1000)
            await dismiss_popups(page)

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

            # Wait for content check (3 minutes) while continuously dismissing popups
            logger.info("Waiting 3 minutes for content check...")
            for _ in range(36):  # 36 x 5 seconds = 3 minutes
                await dismiss_popups(page)
                await page.wait_for_timeout(5000)
            logger.info("Content check wait done!")

            await page.wait_for_timeout(1000)
            await page.screenshot(path="before_post.png")

            # Click post button
            posted = await click_post_button(page)
            if not posted:
                await page.screenshot(path="post_failed.png")
                raise Exception("Could not find or click the Post button")

            # Handle "Post now" confirmation popup
            await handle_post_confirmation(page)

            # Handle "Content may be limited" warning popup
            await page.wait_for_timeout(2000)
            warning_texts = [
                'text="Content kan worden beperkt"',
                'text="Content may be limited"',
            ]
            for text in warning_texts:
                try:
                    if await page.locator(text).is_visible(timeout=2000):
                        logger.info("Content warning popup detected, closing...")
                        close_btn = page.locator('svg[class*="close"], button[class*="close"], [data-e2e="modal-close-button"]').first
                        try:
                            await close_btn.click(timeout=2000)
                        except Exception:
                            try:
                                await page.locator('text="Content kan worden beperkt"').locator('..').locator('..').locator('button').first.click()
                            except Exception:
                                await page.keyboard.press("Escape")
                        await page.wait_for_timeout(1000)
                        logger.info("Closed content warning, clicking post again...")
                        await click_post_button(page)
                        await handle_post_confirmation(page)
                        break
                except Exception:
                    pass

            await page.wait_for_timeout(6000)
            return {"success": True}

        except Exception as e:
            logger.error(f"post_video error: {e}")
            raise
        finally:
            await browser.close()