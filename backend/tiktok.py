import asyncio
import json
import os
import logging
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


async def get_account_info(cookies: list) -> dict:
    """Scrape basic account info from TikTok using saved cookies."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(user_agent=USER_AGENT)

        try:
            await context.add_cookies(cookies)
            page = await context.new_page()

            # Land on TikTok home to detect logged-in username
            await page.goto(
                "https://www.tiktok.com/", wait_until="domcontentloaded", timeout=30000
            )
            await page.wait_for_timeout(3000)

            username = None

            # Try sidebar profile link first
            try:
                link = await page.query_selector('[data-e2e="nav-profile"]')
                if link:
                    href = await link.get_attribute("href") or ""
                    if "/@" in href:
                        username = href.split("/@")[1].strip("/")
            except Exception:
                pass

            # Fallback: look at any /@ anchor
            if not username:
                try:
                    anchors = await page.query_selector_all('a[href*="/@"]')
                    for a in anchors:
                        href = await a.get_attribute("href") or ""
                        if "/@" in href:
                            candidate = href.split("/@")[1].strip("/")
                            if candidate and "/" not in candidate:
                                username = candidate
                                break
                except Exception:
                    pass

            if not username:
                raise Exception(
                    "Could not detect logged-in user — are these valid TikTok cookies?"
                )

            # Go to that profile page
            await page.goto(
                f"https://www.tiktok.com/@{username}",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            await page.wait_for_timeout(3000)

            def safe_text(el):
                return el

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
                        locals()[attr]  # just reference it
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
    """Post a video to TikTok using saved session cookies."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS)
        context = await browser.new_context(user_agent=USER_AGENT)

        try:
            await context.add_cookies(cookies)
            page = await context.new_page()

            await page.goto(
                "https://www.tiktok.com/upload",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            await page.wait_for_timeout(3000)

            # Dismiss cookie consent if present
            for btn_text in ["Accept all", "Accept All", "Accept", "Decline optional"]:
                try:
                    btn = page.get_by_role("button", name=btn_text)
                    if await btn.is_visible(timeout=2000):
                        await btn.click()
                        await page.wait_for_timeout(1000)
                        break
                except Exception:
                    pass

            # --- Locate the upload iframe ---
            iframe_locator = page.frame_locator("iframe").first
            # Wait for the file input inside the iframe
            file_input = iframe_locator.locator('input[type="file"]')
            await file_input.wait_for(timeout=15000)
            await file_input.set_input_files(video_path)
            logger.info("Video file set — waiting for processing...")

            # Wait for upload + encoding to finish (TikTok shows a progress bar)
            await page.wait_for_timeout(10000)

            # --- Caption ---
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
                        # Clear existing content then type
                        await el.press("Control+a")
                        await el.type(caption, delay=30)
                        caption_added = True
                        logger.info("Caption added")
                        break
                except Exception:
                    pass

            if not caption_added:
                logger.warning("Could not find caption input; posting without caption")

            await page.wait_for_timeout(1000)

            # --- Post button ---
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
                        logger.info("Post button clicked")
                        break
                except Exception:
                    pass

            if not posted:
                raise Exception("Could not find or click the Post button")

            # Wait for success / redirect
            await page.wait_for_timeout(6000)
            return {"success": True}

        except Exception as e:
            logger.error(f"post_video error: {e}")
            raise
        finally:
            await browser.close()
