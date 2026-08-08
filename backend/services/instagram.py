import logging
import json

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

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


async def get_instagram_account_info(cookies: list) -> dict:
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
            await page.goto("https://www.instagram.com/", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)
            logger.warning(f"Instagram page URL after load: {page.url}")

            user = await page.evaluate("""
                () => {
                    try {
                        const sd = window._sharedData;
                        if (sd && sd.config && sd.config.viewer) {
                            const v = sd.config.viewer;
                            return {
                                username: v.username,
                                full_name: v.full_name,
                                profile_pic_url: v.profile_pic_url_hd || v.profile_pic_url,
                                follower_count: v.edge_followed_by ? v.edge_followed_by.count : 0,
                                following_count: v.edge_follow ? v.edge_follow.count : 0,
                                media_count: v.edge_owner_to_timeline_media ? v.edge_owner_to_timeline_media.count : 0,
                            };
                        }
                        const scripts = document.querySelectorAll('script[type="application/json"]');
                        for (const s of scripts) {
                            try {
                                const d = JSON.parse(s.textContent);
                                const u = d?.data?.user || d?.user;
                                if (u && u.username) return u;
                            } catch {}
                        }
                        return null;
                    } catch(e) {
                        return {error: e.toString()};
                    }
                }
            """)
            logger.warning(f"Instagram page JS user: {user}")

            if not user or not user.get("username"):
                await page.goto("https://www.instagram.com/accounts/edit/", wait_until="domcontentloaded", timeout=20000)
                await page.wait_for_timeout(2000)
                logger.warning(f"Instagram accounts/edit URL: {page.url}")
                user = await page.evaluate("""
                    () => {
                        try {
                            const sd = window._sharedData;
                            if (sd && sd.config && sd.config.viewer) {
                                const v = sd.config.viewer;
                                return {
                                    username: v.username,
                                    full_name: v.full_name,
                                    profile_pic_url: v.profile_pic_url_hd || v.profile_pic_url,
                                    follower_count: v.edge_followed_by ? v.edge_followed_by.count : 0,
                                    following_count: v.edge_follow ? v.edge_follow.count : 0,
                                    media_count: 0,
                                };
                            }
                            return null;
                        } catch(e) { return {error: e.toString()}; }
                    }
                """)
                logger.warning(f"Instagram accounts/edit JS user: {user}")

            await browser.close()

            if user and user.get("username"):
                logger.info(f"Instagram account verified: {user.get('username')}")
                return {
                    "username": user.get("username", ""),
                    "display_name": user.get("full_name") or user.get("username", ""),
                    "avatar_url": user.get("profile_pic_url_hd") or user.get("profile_pic_url", ""),
                    "followers": str(user.get("follower_count", user.get("edge_followed_by", {}).get("count", 0))),
                    "following": str(user.get("following_count", user.get("edge_follow", {}).get("count", 0))),
                    "likes": "0",
                    "views": str(user.get("media_count", 0)),
                }

            logger.error(f"Instagram: could not extract user, final data was: {user}")

        except Exception as e:
            logger.error(f"Instagram Playwright error: {e}", exc_info=True)
            await browser.close()
            raise

    raise Exception("Could not verify Instagram session - please re-export your cookies and try again")