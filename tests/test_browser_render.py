import asyncio
import os
import unittest
from playwright.async_api import async_playwright

class TestBrowserRender(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        os.makedirs("tests/screenshots", exist_ok=True)
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=True)

    async def asyncTearDown(self):
        await self.browser.close()
        await self.playwright.stop()

    async def test_01_homepage_normal_flow(self):
        """Test standard homepage load: intro appears and dismisses within 8s, hero and posters visible."""
        context = await self.browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()

        console_errors = []
        page.on("pageerror", lambda err: console_errors.append(str(err)))

        await page.goto("http://localhost:5000", wait_until="domcontentloaded")

        # 1. Check intro at 1.5s
        await asyncio.sleep(1.5)
        headline = await page.query_selector("#openingHeadline")
        self.assertIsNotNone(headline, "Opening headline must exist during intro")

        # 2. Wait for auto-dismiss (must happen within 8s)
        intro_gone = False
        for _ in range(16):
            await asyncio.sleep(0.5)
            is_gone = await page.evaluate("""() => {
                const el = document.getElementById('openingScreen');
                if (!el) return true;
                const style = window.getComputedStyle(el);
                return style.display === 'none' || el.classList.contains('dismissed');
            }""")
            if is_gone:
                intro_gone = True
                break

        self.assertTrue(intro_gone, "Intro overlay must be dismissed or removed within 8s")

        # 3. Assert hero, carousel, and navbar are visible
        navbar_visible = await page.is_visible(".navbar")
        hero_visible = await page.is_visible("#hero")
        carousel_visible = await page.is_visible("#carousel3dTrack")
        self.assertTrue(navbar_visible, "Navbar must be visible")
        self.assertTrue(hero_visible, "Hero section must be visible")
        self.assertTrue(carousel_visible, "Carousel 3D track must be visible")

        # 4. Assert at least 4 poster images are visible in the DOM
        await page.wait_for_selector(".card-poster-img", timeout=12000)
        await page.wait_for_function("""() => {
            const imgs = Array.from(document.querySelectorAll('.poster-img, .card-poster-img, .rec-poster-img, .search-result-poster'));
            return imgs.length >= 4 && imgs.filter(img => img.naturalWidth > 0 || img.complete).length >= 4;
        }""", timeout=12000)
        poster_count = await page.evaluate("""() => {
            const imgs = Array.from(document.querySelectorAll('.poster-img, .card-poster-img, .rec-poster-img, .search-result-poster'));
            return imgs.filter(img => img.naturalWidth > 0 || img.complete).length;
        }""")
        self.assertGreaterEqual(poster_count, 4, f"At least 4 posters must load (found {poster_count})")

        # 5. Assert zero uncaught exceptions
        self.assertEqual(len(console_errors), 0, f"Uncaught page errors: {console_errors}")

        await page.screenshot(path="tests/screenshots/homepage_normal.png", full_page=False)
        print("PASS: test_01_homepage_normal_flow")

    async def test_02_homepage_blocked_cdns(self):
        """Test homepage resilience when cdnjs, youtube, and googleapis are completely blocked."""
        context = await self.browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()

        console_errors = []
        page.on("pageerror", lambda err: console_errors.append(str(err)))

        # Block external CDNs
        async def route_intercept(route):
            url = route.request.url
            if any(domain in url for domain in ["cdnjs.cloudflare.com", "youtube.com", "googleapis.com", "gstatic.com"]):
                await route.abort()
            else:
                await route.continue_()

        await page.route("**/*", route_intercept)

        await page.goto("http://localhost:5000", wait_until="domcontentloaded")

        # Intro should fail-safe or dismiss within 8s
        intro_gone = False
        for _ in range(16):
            await asyncio.sleep(0.5)
            is_gone = await page.evaluate("""() => {
                const el = document.getElementById('openingScreen');
                if (!el) return true;
                const style = window.getComputedStyle(el);
                return style.display === 'none' || el.classList.contains('dismissed');
            }""")
            if is_gone:
                intro_gone = True
                break

        self.assertTrue(intro_gone, "Intro must be dismissed even when CDNs are blocked")

        # Hero and local vendor libraries must still be functional
        has_gsap = await page.evaluate("() => typeof window.gsap !== 'undefined'")
        self.assertTrue(has_gsap, "Local self-hosted GSAP must load from /static/vendor/")

        hero_visible = await page.is_visible("#hero")
        self.assertTrue(hero_visible, "Hero must be visible with blocked CDNs")

        # Check backdrop image is visible and page did not crash
        backdrop_opacity = await page.evaluate("""() => {
            const img = document.getElementById('heroBackdropImg');
            return img ? window.getComputedStyle(img).opacity : '0';
        }""")
        self.assertEqual(backdrop_opacity, "1", "Hero backdrop must remain visible when YouTube is blocked")

        self.assertEqual(len(console_errors), 0, f"Uncaught errors with blocked CDNs: {console_errors}")

        await page.screenshot(path="tests/screenshots/homepage_blocked_cdns.png", full_page=False)
        print("PASS: test_02_homepage_blocked_cdns")

    async def test_03_click_skip_button(self):
        """Test clicking Skip immediately dismisses the intro."""
        context = await self.browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()

        await page.goto("http://localhost:5000", wait_until="domcontentloaded")
        await asyncio.sleep(0.4)

        # Click Skip
        skip_btn = await page.query_selector("#openingSkipBtn")
        self.assertIsNotNone(skip_btn)
        await skip_btn.click()

        await asyncio.sleep(0.8)
        intro_gone = await page.evaluate("""() => {
            const el = document.getElementById('openingScreen');
            return !el || el.classList.contains('dismissed') || window.getComputedStyle(el).display === 'none';
        }""")
        self.assertTrue(intro_gone, "Intro must be dismissed after clicking Skip")

        body_overflow = await page.evaluate("() => window.getComputedStyle(document.body).overflow")
        self.assertNotEqual(body_overflow, "hidden", "Body scroll must be unlocked after Skip")

        await page.screenshot(path="tests/screenshots/after_skip.png", full_page=False)
        print("PASS: test_03_click_skip_button")

    async def test_04_nointro_param(self):
        """Test ?nointro=1 parameter bypasses the intro entirely."""
        context = await self.browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()

        await page.goto("http://localhost:5000?nointro=1", wait_until="domcontentloaded")
        await asyncio.sleep(0.5)

        intro_gone = await page.evaluate("""() => {
            const el = document.getElementById('openingScreen');
            return !el || el.classList.contains('dismissed') || window.getComputedStyle(el).display === 'none';
        }""")
        self.assertTrue(intro_gone, "Intro must be immediately bypassed when ?nointro=1")

        hero_visible = await page.is_visible("#hero")
        self.assertTrue(hero_visible, "Hero must be immediately visible with ?nointro=1")
        print("PASS: test_04_nointro_param")

    async def test_05_watchlist_navigation_and_bookmark(self):
        """Test bookmarking a card, undo toast, and navigating to /watchlist."""
        context = await self.browser.new_context(viewport={"width": 1400, "height": 900})
        page = await context.new_page()

        await page.goto("http://localhost:5000?nointro=1", wait_until="domcontentloaded")
        await asyncio.sleep(1.0)

        # Bookmark hero active movie
        add_btn = await page.query_selector("#heroAddListBtn")
        self.assertIsNotNone(add_btn, "Hero Add to Watchlist button must exist")
        await add_btn.click()
        await asyncio.sleep(0.5)

        # Check badge count
        badge_text = await page.inner_text("#navWatchlistBadge")
        self.assertNotEqual(badge_text, "0", "Navbar badge must increment after adding to watchlist")

        # Check Toast
        toast_visible = await page.is_visible("#toast.show")
        self.assertTrue(toast_visible, "Undo toast must appear after adding to watchlist")

        # Navigate to /watchlist
        wl_link = await page.query_selector("#navWatchlistLink")
        await wl_link.click()
        await page.wait_for_url("**/watchlist")

        # Verify /watchlist page elements
        await asyncio.sleep(1.0)
        wl_title = await page.is_visible(".watchlist-title")
        wl_grid = await page.is_visible("#watchlistGrid")
        self.assertTrue(wl_title, "Watchlist title must be visible")
        self.assertTrue(wl_grid, "Watchlist grid must be visible")

        # At least 1 card in watchlist
        card_count = await page.evaluate("() => document.querySelectorAll('.watchlist-card').length")
        self.assertGreaterEqual(card_count, 1, "At least 1 saved card must be rendered in watchlist")

        await page.screenshot(path="tests/screenshots/watchlist_page.png", full_page=False)
        print("PASS: test_05_watchlist_navigation_and_bookmark")

    async def test_06_recommended_and_culture_layout_1280px(self):
        """Test layout at 1280px width: separate sections, no heading/row overlap, distinct container IDs."""
        context = await self.browser.new_context(viewport={"width": 1280, "height": 900})
        page = await context.new_page()

        await page.goto("http://localhost:5000?nointro=1", wait_until="domcontentloaded")
        await asyncio.sleep(1.5)

        # Check recommended section layout
        rec_header = await page.locator("#recommendedHeader").bounding_box()
        rec_row = await page.locator("#recRow").bounding_box()
        self.assertIsNotNone(rec_header)
        self.assertIsNotNone(rec_row)
        self.assertLessEqual(rec_header["y"] + rec_header["height"], rec_row["y"] + 5,
                             "Recommended header must not overlap recRow at 1280px")

        # Check cross-culture section layout
        cc_header = await page.locator("#crossCultureHeader").bounding_box()
        cc_row = await page.locator("#crossCultureRow").bounding_box()
        self.assertIsNotNone(cc_header)
        self.assertIsNotNone(cc_row)
        self.assertLessEqual(cc_header["y"] + cc_header["height"], cc_row["y"] + 5,
                             "Cross-culture header must not overlap crossCultureRow at 1280px")

        # Check separation between recommended section and cross culture section
        rec_sec = await page.locator("#recommended").bounding_box()
        cc_sec = await page.locator("#crossCultureSection").bounding_box()
        self.assertIsNotNone(rec_sec)
        self.assertIsNotNone(cc_sec)
        self.assertLessEqual(rec_sec["y"] + rec_sec["height"], cc_sec["y"] + 5,
                             "Recommended section must not overlap cross-culture section at 1280px")

        await page.screenshot(path="tests/screenshots/layout_1280px.png", full_page=False)
        print("PASS: test_06_recommended_and_culture_layout_1280px")

    async def test_07_recommended_and_culture_layout_390px(self):
        """Test mobile layout at 390px width: no overlapping or clipped section headings."""
        context = await self.browser.new_context(viewport={"width": 390, "height": 844})
        page = await context.new_page()

        await page.goto("http://localhost:5000?nointro=1", wait_until="domcontentloaded")
        await asyncio.sleep(1.5)

        # Check recommended section
        rec_header = await page.locator("#recommendedHeader").bounding_box()
        rec_row = await page.locator("#recRow").bounding_box()
        self.assertIsNotNone(rec_header)
        self.assertIsNotNone(rec_row)
        self.assertLessEqual(rec_header["y"] + rec_header["height"], rec_row["y"] + 5,
                             "Recommended header must not overlap recRow at 390px")

        # Check cross-culture section
        cc_header = await page.locator("#crossCultureHeader").bounding_box()
        cc_row = await page.locator("#crossCultureRow").bounding_box()
        self.assertIsNotNone(cc_header)
        self.assertIsNotNone(cc_row)
        self.assertLessEqual(cc_header["y"] + cc_header["height"], cc_row["y"] + 5,
                             "Cross-culture header must not overlap crossCultureRow at 390px")

        await page.screenshot(path="tests/screenshots/layout_390px.png", full_page=False)
        print("PASS: test_07_recommended_and_culture_layout_390px")

    async def test_08_scrollbar_hidden_and_scroll_controls(self):
        """Test that native scrollbars are hidden and arrow buttons/drag controls exist."""
        context = await self.browser.new_context(viewport={"width": 1280, "height": 900})
        page = await context.new_page()

        await page.goto("http://localhost:5000?nointro=1", wait_until="domcontentloaded")
        await asyncio.sleep(1.5)

        # Check scrollbar-width computed style
        rec_scrollbar_width = await page.evaluate(
            "() => window.getComputedStyle(document.getElementById('recRow')).scrollbarWidth"
        )
        self.assertEqual(rec_scrollbar_width, "none", "recRow must have scrollbar-width: none")

        cc_scrollbar_width = await page.evaluate(
            "() => window.getComputedStyle(document.getElementById('crossCultureRow')).scrollbarWidth"
        )
        self.assertEqual(cc_scrollbar_width, "none", "crossCultureRow must have scrollbar-width: none")

        # Verify arrow buttons exist
        rec_prev = await page.query_selector("#recRowPrev")
        rec_next = await page.query_selector("#recRowNext")
        cc_prev = await page.query_selector("#crossCulturePrev")
        cc_next = await page.query_selector("#crossCultureNext")
        self.assertIsNotNone(rec_prev, "recRowPrev button must exist")
        self.assertIsNotNone(rec_next, "recRowNext button must exist")
        self.assertIsNotNone(cc_prev, "crossCulturePrev button must exist")
        self.assertIsNotNone(cc_next, "crossCultureNext button must exist")

        print("PASS: test_08_scrollbar_hidden_and_scroll_controls")

    async def test_09_model_dropdown_and_cold_start_note(self):
        """Test model dropdown switch and cold-start note display."""
        context = await self.browser.new_context(viewport={"width": 1280, "height": 900})
        page = await context.new_page()

        await page.goto("http://localhost:5000?nointro=1", wait_until="domcontentloaded")
        await asyncio.sleep(1.5)

        # Check cold-start note is visible for user with < 3 ratings
        note_text = await page.inner_text("#recommendedNote")
        self.assertEqual(note_text, "Rate 3 movies to personalise. Showing popular picks")

        # Check model dropdown
        select = await page.query_selector("#modelSelect")
        self.assertIsNotNone(select)
        await page.select_option("#modelSelect", "knn")
        await asyncio.sleep(1.0)
        selected_val = await page.input_value("#modelSelect")
        self.assertEqual(selected_val, "knn", "Model dropdown must be selectable to KNN")

        # Check cross-culture row contains language chips and cards
        chip_count = await page.evaluate("() => document.querySelectorAll('#crossCultureRow .lang-chip').length")
        self.assertGreater(chip_count, 0, "Cross-culture row must render language chips")

        print("PASS: test_09_model_dropdown_and_cold_start_note")

if __name__ == "__main__":
    unittest.main()
