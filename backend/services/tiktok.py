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
                        browser = await pw.chromium.launch(
                            headless=HEADLESS,
                            args=[
                                "--no-sandbox",
                                "--disable-setuid-sandbox",
                                "--disable-blink-features=AutomationControlled",
                                "--disable-dev-shm-usage",
                            ],
                        )
                        ctx = await browser.new_context(
                            user_agent=USER_AGENT,
                            viewport={"width": 1280, "height": 800},
                        )
                        await ctx.add_init_script(
                            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
                        )
                        await ctx.add_cookies(normalize_cookies(cookies))
                        pg = await ctx.new_page()

                        await pg.goto(f"https://www.tiktok.com/@{username}", wait_until="domcontentloaded", timeout=30000)
                        await pg.wait_for_timeout(3000)

                        # Pull avatar, secUid and stats straight out of the SSR rehydration
                        # payload embedded in the page — TikTok often renders the profile
                        # server-side, so the old data-e2e DOM selectors / XHR sniffing
                        # would come back empty.
                        page_data = await pg.evaluate("""
                            () => {
                                try {
                                    const script = document.querySelector('#__UNIVERSAL_DATA_FOR_REHYDRATION__');
                                    if (!script) return null;
                                    const json = JSON.parse(script.textContent);
                                    const userDetail = json?.__DEFAULT_SCOPE__?.['webapp.user-detail'];
                                    const user = userDetail?.userInfo?.user;
                                    const stats = userDetail?.userInfo?.stats;
                                    if (!user) return null;
                                    return {
                                        secUid: user.secUid || '',
                                        avatarUrl: user.avatarLarger || user.avatarMedium || user.avatarThumb || '',
                                        followers: stats?.followerCount ?? 0,
                                        following: stats?.followingCount ?? 0,
                                        likes: stats?.heartCount ?? 0,
                                    };
                                } catch (e) {
                                    return { error: String(e) };
                                }
                            }
                        """)
                        logger.info(f"Page data for {username}: {page_data}")

                        page_data = page_data or {}
                        sec_uid = page_data.get("secUid", "")
                        avatar_url = page_data.get("avatarUrl", "") or avatar_url
                        followers = str(page_data.get("followers", followers))
                        following = str(page_data.get("following", following))
                        likes = str(page_data.get("likes", likes))

                        # Fallback: try old DOM selectors in case rehydration payload
                        # is missing/renamed but the stats are still rendered visibly.
                        if not page_data.get("secUid") and page_data.get("followers") is None:
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
                                followers = stats.get("followers") or followers
                                following = stats.get("following") or following
                                likes     = stats.get("likes") or likes
                                logger.info(f"Fallback DOM stats for {username}: {stats}")

                        print(f">>> secUid: {sec_uid}", flush=True)

                        total_views = 0
                        try:
                            await pg.screenshot(path="tiktok_profile_before_scroll.png")
                            scrape_result = await pg.evaluate("""
                                async () => {
                                    const parseCount = (text) => {
                                        if (!text) return 0;
                                        text = text.trim().toUpperCase().replace(/,/g, '');
                                        if (text.endsWith('K')) return Math.round(parseFloat(text) * 1000);
                                        if (text.endsWith('M')) return Math.round(parseFloat(text) * 1000000);
                                        if (text.endsWith('B')) return Math.round(parseFloat(text) * 1000000000);
                                        const n = parseInt(text, 10);
                                        return isNaN(n) ? 0 : n;
                                    };

                                    const itemSelectors = [
                                        '[data-e2e="user-post-item"]',
                                        '[data-e2e="user-post-item-list"] > div',
                                        'div[class*="DivItemContainer"]',
                                        'a[href*="/video/"]',
                                    ];
                                    const viewSelectors = [
                                        '[data-e2e="video-views"]',
                                        'strong[data-e2e="video-views"]',
                                        'strong[class*="video-count"]',
                                        'div[class*="video-count"]',
                                        'span[class*="video-count"]',
                                    ];

                                    // Scroll to trigger lazy-loading of all video tiles
                                    let lastCount = -1;
                                    let stableRounds = 0;
                                    for (let i = 0; i < 40; i++) {
                                        window.scrollTo(0, document.body.scrollHeight);
                                        await new Promise(r => setTimeout(r, 700));
                                        let curCount = 0;
                                        for (const s of itemSelectors) {
                                            const c = document.querySelectorAll(s).length;
                                            if (c > curCount) curCount = c;
                                        }
                                        if (curCount === lastCount) {
                                            stableRounds += 1;
                                            if (stableRounds >= 3) break;
                                        } else {
                                            stableRounds = 0;
                                        }
                                        lastCount = curCount;
                                    }

                                    let items = [];
                                    let usedItemSelector = null;
                                    for (const s of itemSelectors) {
                                        const found = document.querySelectorAll(s);
                                        if (found.length > items.length) {
                                            items = Array.from(found);
                                            usedItemSelector = s;
                                        }
                                    }

                                    let usedViewSelector = null;
                                    let total = 0;
                                    const samples = [];
                                    items.forEach((item, idx) => {
                                        let text = null;
                                        for (const vs of viewSelectors) {
                                            const el = item.matches && item.matches(vs) ? item : item.querySelector(vs);
                                            if (el && el.innerText) {
                                                text = el.innerText;
                                                if (!usedViewSelector) usedViewSelector = vs;
                                                break;
                                            }
                                        }
                                        const count = parseCount(text);
                                        total += count;
                                        if (idx < 5) samples.push(text);
                                    });

                                    // Extra diagnostics: page state signals
                                    const bodyText = document.body.innerText.slice(0, 300);
                                    const hasPrivateBadge = /private/i.test(document.body.innerText);
                                    const hasNoContent = /no videos|geen video/i.test(document.body.innerText);
                                    const hasCaptcha = /slider|puzzle|captcha|verify you.?re human/i.test(document.body.innerText);

                                    return {
                                        total, count: items.length, samples,
                                        usedItemSelector, usedViewSelector,
                                        hasPrivateBadge, hasNoContent, hasCaptcha, bodyTextSnippet: bodyText,
                                    };
                                }
                            """)
                            total_views = scrape_result.get("total", 0)

                            # If TikTok showed a captcha, wait a bit and retry once —
                            # with a visible (non-headless) browser + real cookies it
                            # often clears on its own within a few seconds.
                            if scrape_result.get("hasCaptcha") and scrape_result.get("count", 0) == 0:
                                print(">>> CAPTCHA DETECTED, waiting 8s and retrying scrape once...", flush=True)
                                await pg.wait_for_timeout(8000)
                                await pg.screenshot(path="tiktok_profile_after_captcha_wait.png")
                                scrape_result = await pg.evaluate("""
                                    async () => {
                                        const parseCount = (text) => {
                                            if (!text) return 0;
                                            text = text.trim().toUpperCase().replace(/,/g, '');
                                            if (text.endsWith('K')) return Math.round(parseFloat(text) * 1000);
                                            if (text.endsWith('M')) return Math.round(parseFloat(text) * 1000000);
                                            if (text.endsWith('B')) return Math.round(parseFloat(text) * 1000000000);
                                            const n = parseInt(text, 10);
                                            return isNaN(n) ? 0 : n;
                                        };
                                        const itemSelectors = [
                                            '[data-e2e="user-post-item"]',
                                            '[data-e2e="user-post-item-list"] > div',
                                            'div[class*="DivItemContainer"]',
                                            'a[href*="/video/"]',
                                        ];
                                        const viewSelectors = [
                                            '[data-e2e="video-views"]',
                                            'strong[data-e2e="video-views"]',
                                            'strong[class*="video-count"]',
                                            'div[class*="video-count"]',
                                            'span[class*="video-count"]',
                                        ];
                                        let lastCount = -1;
                                        let stableRounds = 0;
                                        for (let i = 0; i < 40; i++) {
                                            window.scrollTo(0, document.body.scrollHeight);
                                            await new Promise(r => setTimeout(r, 700));
                                            let curCount = 0;
                                            for (const s of itemSelectors) {
                                                const c = document.querySelectorAll(s).length;
                                                if (c > curCount) curCount = c;
                                            }
                                            if (curCount === lastCount) {
                                                stableRounds += 1;
                                                if (stableRounds >= 3) break;
                                            } else {
                                                stableRounds = 0;
                                            }
                                            lastCount = curCount;
                                        }
                                        let items = [];
                                        let usedItemSelector = null;
                                        for (const s of itemSelectors) {
                                            const found = document.querySelectorAll(s);
                                            if (found.length > items.length) {
                                                items = Array.from(found);
                                                usedItemSelector = s;
                                            }
                                        }
                                        let usedViewSelector = null;
                                        let total = 0;
                                        const samples = [];
                                        items.forEach((item, idx) => {
                                            let text = null;
                                            for (const vs of viewSelectors) {
                                                const el = item.matches && item.matches(vs) ? item : item.querySelector(vs);
                                                if (el && el.innerText) {
                                                    text = el.innerText;
                                                    if (!usedViewSelector) usedViewSelector = vs;
                                                    break;
                                                }
                                            }
                                            const count = parseCount(text);
                                            total += count;
                                            if (idx < 5) samples.push(text);
                                        });
                                        const bodyText = document.body.innerText.slice(0, 300);
                                        const hasCaptcha = /slider|puzzle|captcha|verify you.?re human/i.test(document.body.innerText);
                                        return { total, count: items.length, samples, usedItemSelector, usedViewSelector, hasCaptcha, bodyTextSnippet: bodyText };
                                    }
                                """)
                                total_views = scrape_result.get("total", 0)

                            logger.info(f"Views scrape debug for {username}: {scrape_result}")
                            print(
                                f">>> VIEWS: {total_views} (videos={scrape_result.get('count')}, "
                                f"itemSel={scrape_result.get('usedItemSelector')}, "
                                f"viewSel={scrape_result.get('usedViewSelector')}, "
                                f"captcha={scrape_result.get('hasCaptcha')}, "
                                f"private={scrape_result.get('hasPrivateBadge')}, "
                                f"noContent={scrape_result.get('hasNoContent')})",
                                flush=True,
                            )
                            print(f">>> VIEWS BODY SNIPPET: {scrape_result.get('bodyTextSnippet')!r}", flush=True)
                        except Exception as ve:
                            print(f">>> VIEWS ERROR: {ve}", flush=True)
                            logger.warning(f"Could not scrape views for {username}: {ve}")

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