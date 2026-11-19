import os
import sys
import uuid
import asyncio
from playwright.async_api import async_playwright

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

os.makedirs("tests/screenshots", exist_ok=True)

def log(msg):
    print(msg, flush=True)

async def test_auth_browser_flow():
    test_user = f"cine_{uuid.uuid4().hex[:6]}"
    test_pass = "SecurePass123!"
    display_name = f"Tester {test_user}"

    log(f"[TEST] Starting browser auth test for user: {test_user}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()

        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)

        # 1. Open login page
        log("[TEST] Step 1: Navigating to /login?signup=1")
        await page.goto("http://localhost:5000/login?signup=1", wait_until="networkidle")
        await page.screenshot(path="tests/screenshots/step1_signup_page.png")

        # 2. Fill registration form
        log("[TEST] Step 2: Submitting registration form")
        await page.fill("#regUsername", test_user)
        await page.fill("#regDisplayName", display_name)
        await page.fill("#regPassword", test_pass)
        await page.click("#signupSubmitBtn")

        # 3. Wait for redirect to /profile
        log("[TEST] Step 3: Waiting for redirect to /profile")
        await page.wait_for_url("**/profile", timeout=8000)
        await page.wait_for_selector("#avatarGrid", timeout=5000)
        await page.screenshot(path="tests/screenshots/step2_profile_page.png")

        # 4. Modify preferences
        log("[TEST] Step 4: Modifying preferences (avatar, genres, save)")
        # Click avatar-2 (Sci-Fi Explorer)
        avatar_opt = page.locator('.avatar-option[data-avatar="avatar-2"]')
        if await avatar_opt.count() > 0:
            await avatar_opt.click()

        # Click genre 'Action' and 'Sci-Fi'
        action_pill = page.locator('.pill-btn[data-genre="Action"]')
        if await action_pill.count() > 0:
            await action_pill.click()

        # Save preferences
        await page.click("#savePreferencesBtn")
        await page.wait_for_timeout(1000)
        await page.screenshot(path="tests/screenshots/step3_preferences_saved.png")

        # 5. Navigate to Home and check navbar avatar
        log("[TEST] Step 5: Checking homepage navbar for authenticated user")
        await page.goto("http://localhost:5000/?nointro=1", wait_until="networkidle")
        await page.wait_for_selector("#navUserWrap", state="visible", timeout=6000)
        avatar_name = await page.locator("#navAvatarName").inner_text()
        log(f"[TEST] Navbar user display name: {avatar_name}")
        assert test_user in avatar_name or display_name in avatar_name
        await page.screenshot(path="tests/screenshots/step4_navbar_authenticated.png")

        # 6. Click dropdown and Log out
        log("[TEST] Step 6: Testing logout")
        await page.click("#navAvatarBtn")
        await page.wait_for_selector("#navMenuLogoutBtn", state="visible")
        await page.click("#navMenuLogoutBtn")
        await page.wait_for_timeout(1500)

        # 7. Verify logged out state (navLoginBtn visible)
        login_btn_visible = await page.locator("#navLoginBtn").is_visible()
        print(f"[TEST] Sign In button visible after logout: {login_btn_visible}")
        assert login_btn_visible is True
        await page.screenshot(path="tests/screenshots/step5_logged_out.png")

        await browser.close()

    print("[TEST] ALL BROWSER AUTH TESTS PASSED SUCCESSFULLY!")
    if console_errors:
        print(f"[WARN] Console errors detected: {console_errors}")

if __name__ == "__main__":
    asyncio.run(test_auth_browser_flow())
