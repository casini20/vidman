import logging
from urllib.parse import unquote

logger = logging.getLogger(__name__)


def get_cookie_value(cookies: list, name: str) -> str:
    for c in cookies:
        if c.get("name") == name:
            return c.get("value", "")
    return ""


async def get_instagram_account_info(cookies: list) -> dict:
    session_id = get_cookie_value(cookies, "sessionid")
    ds_user_id = get_cookie_value(cookies, "ds_user_id")

    if not session_id:
        raise Exception("No sessionid cookie found — please re-export your Instagram cookies")

    # Extract user_id from ds_user_id or from sessionid prefix
    user_id = ds_user_id
    if not user_id and session_id:
        # sessionid format: "46940659139%3Axxx" — user_id is before the first %3A
        decoded = unquote(session_id)
        user_id = decoded.split(":")[0]

    if not user_id:
        raise Exception("Could not extract user ID from cookies")

    # Use user_id as username placeholder — will be shown as @{user_id} until synced
    logger.info(f"Instagram session accepted for user_id={user_id}")
    return {
        "username": f"ig_{user_id}",
        "display_name": f"Instagram {user_id}",
        "avatar_url": "",
        "followers": "0",
        "following": "0",
        "likes": "0",
        "views": "0",
    }


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