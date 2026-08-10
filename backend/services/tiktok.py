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
                followers = "0"
                following = "0"
                likes = "0"
                views = "0"
                try:
                    from playwright.async_api import async_playwright
                    async with async_playwright() as pw:
                        browser = await pw.chromium.launch(headless=True, args=["--no-sandbox", "--disable-setuid-sandbox"])
                        ctx = await browser.new_context(user_agent=USER_AGENT)
                        await ctx.add_cookies(normalize_cookies(cookies))
                        pg = await ctx.new_page()
                        await pg.goto(f"https://www.tiktok.com/@{username}", wait_until="domcontentloaded", timeout=30000)
                        await pg.wait_for_timeout(3000)
                        stats = await pg.evaluate("""
                            () => {
                                const get = (sel) => {
                                    const el = document.querySelector(sel);
                                    return el ? el.innerText.trim() : null;
                                };
                                return {
                                    followers: get('[data-e2e="followers-count"]'),
                                    following: get('[data-e2e="following-count"]'),
                                    likes:     get('[data-e2e="likes-count"]'),
                                };
                            }
                        """)
                        if stats and stats.get("followers") is not None:
                            followers = stats.get("followers") or "0"
                            following = stats.get("following") or "0"
                            likes     = stats.get("likes") or "0"
                            logger.info(f"Stats scraped for {username}: followers={followers} following={following} likes={likes}")
                        else:
                            logger.warning(f"Stats DOM elements not found for {username}, got={stats}")

                        print(f'>>> VIEWS FETCH START for {username}', flush=True)
                        # Fetch all video view counts — extract secUid from page then paginate
                        total_views = 0
                        try:
                            total_views = await pg.evaluate("""
                                async () => {
                                    // Extract secUid from page data
                                    let secUid = '';
                                    try {
                                        const data = window.__UNIVERSAL_DATA_FOR_REHYDRATION__;
                                        const scope = data && data.__DEFAULT_SCOPE__;
                                        const detail = scope && (scope['webapp.user-detail'] || {});
                                        secUid = (detail.userInfo && detail.userInfo.user && detail.userInfo.user.secUid) || '';
                                    } catch(e) {}

                                    if (!secUid) return 'NO_SECUID';

                                    let cursor = 0;
                                    let hasMore = true;
                                    let totalViews = 0;
                                    while (hasMore) {
                                        const url = `https://www.tiktok.com/api/post/item_list/?aid=1988&count=30&cursor=${cursor}&secUid=${secUid}&sourceType=8`;
                                        const resp = await fetch(url, { credentials: 'include' });
                                        const text = await resp.text();
                                        if (!text) break;
                                        const data = JSON.parse(text);
                                        const items = data.itemList || [];
                                        items.forEach(item => {
                                            totalViews += (item.stats && item.stats.playCount) || 0;
                                        });
                                        hasMore = data.hasMore === true && items.length > 0;
                                        cursor = data.cursor || 0;
                                        if (!hasMore) break;
                                    }
                                    return totalViews;
                                }
                            """)
                            print(f">>> VIEWS RESULT for {username}: {total_views}", flush=True)
                        except Exception as ve:
                            logger.warning(f"Could not fetch TikTok views: {ve}")

                        views = str(total_views)
                        await browser.close()
                except Exception as e:
                    print(f">>> STATS EXCEPTION for {username}: {e}", flush=True)
                    logger.warning(f"Could not fetch user stats: {e}")
                return {
                    "username": username,
                    "display_name": display_name or username,
                    "avatar_url": avatar_url,
                    "followers": followers,
                    "following": following,
                    "likes": likes,
                    "views": views,
                }
        except Exception as e:
            logger.error(f"Failed to parse passport API: {e}")

    raise Exception("Could not verify TikTok session - please re-export your cookies and try again")


async def dismiss_popups(page):
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
    checking_texts = [
        "Checking in progress",
        "Checking in uitvoering",
        "Checking in",
    ]
    max_iterations = max_minutes * 6
    for i in range(max_iterations):
        try:
            post_btn = page.locator('button:has-text("Post"), button:has-text("Plaatsen")').first
            if await post_btn.is_enabled(timeout=1000):
                logger.info(f"Content check done — Post button enabled after ~{i * 10}s")
                return
        except Exception:
            pass

        still_checking = False
        for text in checking_texts:
            try:
                visible = await page.locator(f'text="{text}"').is_visible(timeout=1000)
                if visible:
                    still_checking = True
                    break
            except Exception:
                pass
        if not still_checking:
            logger.info(f"Content check done — checking text gone after ~{i * 10}s")
            return

        logger.info(f"Content check still running... ({i * 10}s elapsed)")
        await dismiss_popups(page)
        await page.wait_for_timeout(10000)
    logger.info(f"Content check timed out after {max_minutes} minutes, proceeding anyway")


async def click_post_button(page, run_id: str = "") -> bool:
    all_frames = [page] + list(page.frames)

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
    await page.screenshot(path=f"{run_id}_scrolled_down.png")

    try:
        await page.mouse.click(213, 699)
        logger.info("Clicked Post button via coordinates (213, 699)")
        await page.wait_for_timeout(1000)
        await page.screenshot(path=f"{run_id}_after_coord_click.png")
        return True
    except Exception as e:
        logger.info(f"Coordinate click failed: {e}")

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


async def post_video(cookies: list, video_path: str, caption: str, run_id: str = "") -> dict:
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

            await page.screenshot(path=f"{run_id}_upload_page.png")

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

            for _ in range(6):
                await dismiss_popups(page)
                await page.wait_for_timeout(5000)
            await page.screenshot(path=f"{run_id}_after_upload.png")

            await dismiss_popups(page)
            await page.wait_for_timeout(1000)
            await dismiss_popups(page)

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

            logger.info("Waiting for content check to complete...")
            await dismiss_popups(page)
            await page.wait_for_timeout(10000)
            await wait_for_content_check(page, max_minutes=15)

            await page.wait_for_timeout(1000)
            await page.screenshot(path=f"{run_id}_before_post.png")

            posted = await click_post_button(page, run_id=run_id)
            if not posted:
                await page.screenshot(path=f"{run_id}_post_failed.png")
                raise Exception("Could not find or click the Post button")

            await handle_post_confirmation(page)

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
                        try:
                            await page.mouse.click(957, 93)
                            logger.info("Closed modal via coordinate click on X (957, 93)")
                        except Exception as e:
                            logger.info(f"Coordinate X click failed: {e}")
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
                        await page.screenshot(path=f"{run_id}_after_close_warning.png")
                        await click_post_button(page, run_id=run_id)
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