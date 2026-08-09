import logging

logger = logging.getLogger(__name__)


def get_cookie_value(cookies: list, name: str) -> str:
    for c in cookies:
        if c.get("name") == name:
            return c.get("value", "")
    return ""


async def get_instagram_account_info(cookies: list) -> dict:
    session_id = get_cookie_value(cookies, "sessionid")
    if not session_id:
        raise Exception("No sessionid cookie found — please re-export your Instagram cookies")

    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        context = await browser.new_context(user_agent=USER_AGENT)
        await context.add_cookies(normalize_cookies(cookies))
        page = await context.new_page()

        try:
            # Get username from edit page
            await page.goto("https://www.instagram.com/accounts/edit/", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)

            await page.screenshot(path="ig_edit_page.png")
            logger.warning(f"Edit page URL: {page.url}")

            username = await page.evaluate("""
                () => {
                    // New Instagram layout: username is shown as text under the name in profile card
                    // Try the small text under the display name
                    const subtexts = document.querySelectorAll('span, p, div');
                    for (const el of subtexts) {
                        const t = (el.innerText || '').trim();
                        // Username: short, no spaces, alphanumeric + dots + underscores
                        if (t && t.length < 30 && /^[a-zA-Z0-9._]+$/.test(t) && !t.includes(' ')) {
                            const parent = el.closest('a');
                            if (parent && parent.href && parent.href.includes('instagram.com')) return t;
                        }
                    }
                    // Fallback: try to find from page URL or meta
                    const canonical = document.querySelector('link[rel="canonical"]');
                    if (canonical) {
                        const m = canonical.href.match(/instagram\.com\/([^/]+)\/?$/);
                        if (m) return m[1];
                    }
                    // Try input fields (old layout)
                    const inputs = document.querySelectorAll('input');
                    for (const inp of inputs) {
                        if ((inp.getAttribute('name') || '').toLowerCase() === 'username') return inp.value;
                    }
                    return null;
                }
            """)
            logger.warning(f"Extracted username: {username}")

            if not username:
                raise Exception("Could not extract username from edit page")

            # Get stats from profile page
            await page.goto(f"https://www.instagram.com/{username}/", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)

            stats = await page.evaluate("""
                () => {
                    const counts = document.querySelectorAll('span[class*="x5n08af"]');
                    const headers = document.querySelectorAll('span[class*="xdj266r"]');
                    // Try meta description first
                    const desc = document.querySelector('meta[name="description"]');
                    if (desc) return { desc: desc.content };
                    // Try structured data
                    const scripts = document.querySelectorAll('script[type="application/ld+json"]');
                    for (const s of scripts) {
                        try {
                            const d = JSON.parse(s.textContent);
                            if (d.interactionStatistic) return { ld: d };
                        } catch {}
                    }
                    // Try stat list items
                    const lis = document.querySelectorAll('li');
                    const result = {};
                    lis.forEach(li => {
                        const text = li.innerText || '';
                        if (text.includes('follower')) result.followers = text.replace(/[^0-9.,KMB]/gi, '').trim();
                        if (text.includes('following')) result.following = text.replace(/[^0-9.,KMB]/gi, '').trim();
                        if (text.includes('post')) result.posts = text.replace(/[^0-9.,KMB]/gi, '').trim();
                    });
                    return result;
                }
            """)

            logger.info(f"Instagram stats for {username}: {stats}")

            followers = "0"
            following = "0"
            posts = "0"

            if stats:
                if stats.get("desc"):
                    # Parse "X Followers, Y Following, Z Posts" from meta description
                    import re
                    desc = stats["desc"]
                    fm = re.search(r"([\d,]+)\s*Followers", desc, re.I)
                    fgm = re.search(r"([\d,]+)\s*Following", desc, re.I)
                    pm = re.search(r"([\d,]+)\s*Posts", desc, re.I)
                    if fm: followers = fm.group(1).replace(",", "")
                    if fgm: following = fgm.group(1).replace(",", "")
                    if pm: posts = pm.group(1).replace(",", "")
                elif stats.get("ld"):
                    for stat in stats["ld"].get("interactionStatistic", []):
                        t = stat.get("interactionType", "")
                        v = str(stat.get("userInteractionCount", "0"))
                        if "Follow" in t: followers = v
                else:
                    followers = stats.get("followers", "0") or "0"
                    following = stats.get("following", "0") or "0"
                    posts = stats.get("posts", "0") or "0"

            # Get avatar from profile page
            avatar_url = await page.evaluate("""
                () => {
                    const img = document.querySelector('img[alt*="profile picture"], img[alt*="profiel"]');
                    return img ? img.src : '';
                }
            """)

            await browser.close()
            return {
                "username": username,
                "display_name": username,
                "avatar_url": avatar_url or "",
                "followers": followers,
                "following": following,
                "likes": posts,
                "views": "0",
            }

        except Exception as e:
            await browser.close()
            logger.error(f"Instagram get_account_info error: {e}", exc_info=True)
            raise Exception(f"Could not verify Instagram session: {e}")


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
            cookie["url"] = "https://www.instagram.com"
        exp = cookie.get("expirationDate")
        if exp:
            cookie["expires"] = int(exp)
        cookie.pop("expirationDate", None)
        result.append(cookie)
    return result

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


async def post_instagram_video(cookies: list, video_path: str, caption: str, run_id: str = "") -> dict:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 800},
        )
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")

        try:
            await context.add_cookies(normalize_cookies(cookies))
            page = await context.new_page()

            await page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)
            await page.screenshot(path=f"{run_id}_ig_home.png")

            # Click the Create/+ button in the nav
            create_selectors = [
                'a[href="/create/select/"]',
                'svg[aria-label="New post"]',
                '[aria-label="New post"]',
                'a:has-text("Create")',
            ]
            clicked = False
            for sel in create_selectors:
                try:
                    btn = page.locator(sel).first
                    if await btn.is_visible(timeout=2000):
                        await btn.click()
                        clicked = True
                        logger.info(f"Clicked create via {sel}")
                        break
                except Exception:
                    pass

            if not clicked:
                await page.goto("https://www.instagram.com/create/select/", wait_until="domcontentloaded", timeout=30000)

            await page.wait_for_timeout(2000)
            await page.screenshot(path=f"{run_id}_ig_create.png")

            # Click "Post" from the submenu if visible
            for post_label in ["Post", "Bericht"]:
                try:
                    btn = page.get_by_role("menuitem", name=post_label).or_(
                        page.locator(f'text="{post_label}"').first
                    )
                    if await btn.is_visible(timeout=2000):
                        await btn.click()
                        logger.info(f"Clicked Post submenu: {post_label}")
                        await page.wait_for_timeout(2000)
                        break
                except Exception:
                    pass

            await page.screenshot(path=f"{run_id}_ig_post_modal.png")

            # Wait for file upload button
            file_uploaded = False
            for btn_label in ["Select from computer", "Selecteer van computer", "Van computer selecteren"]:
                try:
                    select_btn = page.get_by_role("button", name=btn_label)
                    if await select_btn.is_visible(timeout=5000):
                        async with page.expect_file_chooser(timeout=10000) as fc_info:
                            await select_btn.click()
                        file_chooser = await fc_info.value
                        await file_chooser.set_files(video_path)
                        logger.info(f"Instagram file set via file chooser: {btn_label}")
                        await page.wait_for_timeout(3000)
                        file_uploaded = True
                        break
                except Exception as e:
                    logger.warning(f"File chooser attempt failed for '{btn_label}': {e}")
            if not file_uploaded:
                await page.screenshot(path=f"{run_id}_ig_no_upload_btn.png")
                raise Exception("Could not find Instagram file upload button")
            await page.screenshot(path=f"{run_id}_ig_after_upload.png")

            # Dismiss "Video posts are now shared as reels" popup
            try:
                ok_btn = page.get_by_role("button", name="OK")
                if await ok_btn.is_visible(timeout=5000):
                    await ok_btn.click()
                    logger.info("Dismissed reels popup")
                    await page.wait_for_timeout(1000)
            except Exception:
                pass

            async def click_top_right_button(labels):
                """Click a button/link by text, scoped to the modal header."""
                for label in labels:
                    for sel in [
                        f'[role="button"]:has-text("{label}")',
                        f'button:has-text("{label}")',
                        f'a:has-text("{label}")',
                        f'div:has-text("{label}")',
                    ]:
                        try:
                            el = page.locator(sel).last  # last = rightmost in DOM
                            if await el.is_visible(timeout=2000):
                                await el.click()
                                logger.info(f"Instagram clicked: {label} via {sel}")
                                return True
                        except Exception:
                            pass
                return False

            # Step 1: Crop → Next
            await page.wait_for_timeout(2000)
            await click_top_right_button(["Next", "Volgende"])
            await page.wait_for_timeout(2000)
            await page.screenshot(path=f"{run_id}_ig_step2.png")

            # Step 2: Edit → Next
            await click_top_right_button(["Next", "Volgende"])
            await page.wait_for_timeout(2000)
            await page.screenshot(path=f"{run_id}_ig_caption.png")

            # Step 3: Caption
            try:
                caption_area = page.locator('div[contenteditable="true"]').first
                if await caption_area.is_visible(timeout=3000):
                    await caption_area.click()
                    await caption_area.type(caption, delay=30)
                    logger.info("Instagram caption added")
                    await page.wait_for_timeout(1000)
            except Exception as e:
                logger.warning(f"Instagram caption failed: {e}")

            # Step 4: Share
            await click_top_right_button(["Share", "Delen", "Publish"])
            logger.info("Instagram Share clicked, waiting for upload to complete...")

            # Wait up to 3 minutes for the Sharing spinner to disappear
            for _ in range(36):  # 36 x 5s = 3 minutes
                await page.wait_for_timeout(5000)
                try:
                    sharing_visible = await page.locator('text="Sharing"').is_visible(timeout=1000)
                    if not sharing_visible:
                        logger.info("Instagram sharing complete")
                        break
                except Exception:
                    break

            await page.screenshot(path=f"{run_id}_ig_after_share.png")
            await browser.close()
            return {"success": True}

        except Exception as e:
            logger.error(f"Instagram post_video error: {e}")
            try:
                await browser.close()
            except Exception:
                pass
            raise