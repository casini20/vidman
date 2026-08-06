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


async def wait_for_content_check(page, max_minutes: int = 15):
    """Poll until 'Checking in progress' is gone, up to max_minutes."""
    checking_texts = [
        "Checking in progress",
        "Checking in uitvoering",  # Dutch
    ]
    max_iterations = max_minutes * 6  # check every 10 seconds
    for i in range(max_iterations):
        still_checking = False
        for text in checking_texts:
            try:
                visible = await page.locator(f'text="{text}"').is_visible(timeout=2000)
                if visible:
                    still_checking = True
                    break
            except Exception:
                pass
        if not still_checking:
            logger.info(f"Content check done after ~{i * 10} seconds")
            return
        elapsed = i * 10
        logger.info(f"Content check still running... ({elapsed}s elapsed)")
        await dismiss_popups(page)
        await page.wait_for_timeout(10000)
    logger.info(f"Content check timed out after {max_minutes} minutes, proceeding anyway")


async def click_post_button(page) -> bool:
    """Try to click the Post/Plaatsen button."""
    all_frames = [page] + list(page.frames)

    # Scroll every frame - target both window and any scrollable container divs
    for frame in all_frames:
        try:
            await frame.evaluate("""
                () => {
                    window.scrollTo(0, 99999);
                    document.documentElement.scrollTop = 99999;
                    document.body.scrollTop = 99999;
                    const divs = Array.from(document.querySelectorAll('div'));
                    divs.sort((a, b) => b.scrollHeight - a.scrollHeight);
                    for (const div of divs.slice(0, 5)) {
                        div.scrollTop = 99999;
                    }
                }
            """)
            await page.wait_for_timeout(500)
        except Exception:
            pass
    await page.wait_for_timeout(1000)
    await page.screenshot(path="scrolled_down.png")

    # Coordinate click first — we know exactly where the Post button is
    try:
        await page.mouse.click(213, 699)
        logger.info("Clicked Post button via coordinates (213, 699)")
        await page.wait_for_timeout(1000)
        await page.screenshot(path="after_coord_click.png")
        return True
    except Exception as e:
        logger.info(f"Coordinate click failed: {e}")

    # Selector fallback
    post_selectors = [
        'button:has-text("Plaatsen")',
        'button:has-text("Post")',
        'button[data-e2e="post-btn"]',
        '[class*="post-btn"]',
        'div[class*="btn-post"]',
        'button[class*="submit"]',
        'div[class*="submit"]',
        'button[class*="publish"]',
        'div[class*="publish"]',
    ]
    for sel in post_selectors:
        for frame in all_frames:
            try:
                btn = frame.locator(sel).first if hasattr(frame, 'locator') else None
                if btn and await btn.is_enabled(timeout=2000):
                    await btn.click()
                    logger.info(f"Clicked post button via {sel}")
                    return True
            except Exception:
                pass

    # JS fallback: scan all frames for a matching button by text
    for frame in all_frames:
        try:
            clicked = await frame.evaluate("""
                () => {
                    const texts = ['plaatsen', 'post', 'publish', 'submit'];
                    const buttons = Array.from(document.querySelectorAll('button, div[role="button"]'));
                    for (const btn of buttons) {
                        const t = (btn.innerText || btn.textContent || '').trim().toLowerCase();
                        if (texts.includes(t) && !btn.disabled) {
                            btn.scrollIntoView({behavior: 'smooth', block: 'center'});
                            btn.click();
                            return true;
                        }
                    }
                    return false;
                }
            """)
            if clicked:
                logger.info(f"Clicked post button via JS fallback on frame: {frame.url}")
                return True
        except Exception as e:
            logger.info(f"JS fallback error on frame: {e}")

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

            # Wait for video to upload while dismissing popups
            for _ in range(6):  # 6 x 5 seconds = 30 seconds
                await dismiss_popups(page)
                await page.wait_for_timeout(5000)
            await page.screenshot(path="after_upload.png")

            # Dismiss any remaining popups
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

            # Extra: poll until TikTok's own "Checking in progress" banner is gone
            await wait_for_content_check(page, max_minutes=15)

            await page.wait_for_timeout(1000)
            await page.screenshot(path="before_post.png")

            # Click post button
            posted = await click_post_button(page)
            if not posted:
                await page.screenshot(path="post_failed.png")
                raise Exception("Could not find or click the Post button")

            # Handle "Post now" confirmation popup
            await handle_post_confirmation(page)

            # Handle "Content may be restricted/limited" warning popup
            await page.wait_for_timeout(2000)
            warning_strings = [
                "Content may be restricted",
                "Content kan worden beperkt",
                "Content may be limited",
            ]
            for text in warning_strings:
                try:
                    if await page.locator(f'text="{text}"').is_visible(timeout=2000):
                        logger.info(f"Content warning popup detected: {text}, closing...")
                        # Coordinate click first — X is at (~957, 93)
                        try:
                            await page.mouse.click(957, 93)
                            logger.info("Closed modal via coordinate click on X (957, 93)")
                        except Exception as e:
                            logger.info(f"Coordinate X click failed: {e}")
                            # Fallback to selectors
                            for close_sel in [
                                '[data-e2e="modal-close-button"]',
                                'button[class*="close"]',
                                'svg[class*="close"]',
                                'button:has-text("×")',
                            ]:
                                try:
                                    btn = page.locator(close_sel).first
                                    if await btn.is_visible(timeout=1000):
                                        await btn.click()
                                        break
                                except Exception:
                                    pass
                        await page.wait_for_timeout(1000)
                        await page.screenshot(path="after_close_warning.png")
                        logger.info("Screenshot saved: after_close_warning.png")
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