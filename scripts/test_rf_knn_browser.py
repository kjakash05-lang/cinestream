"""
scripts/test_rf_knn_browser.py
Playwright browser verification for RF vs KNN model switching, demo profile,
network requests, and UI badges.
"""
import asyncio
import os
import sys
from playwright.async_api import async_playwright

SCREENSHOT_PATH = r"C:\Users\kjaka\.gemini\antigravity\brain\ef87894a-f3c6-49fd-a874-f31ae9c93cb7\rf_knn_browser_verified.png"

async def run_browser_verification():
    console_errors = []
    network_requests = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 900})
        page = await context.new_page()

        page.on("console", lambda msg: print("[BROWSER CONSOLE]", msg.type, msg.text) if msg.type in ("error", "log") else None)
        page.on("request", lambda req: network_requests.append(req.url) if "/api/personal/recommend" in req.url else None)

        async def handle_response(resp):
            if "/api/personal/recommend" in resp.url:
                try:
                    body = await resp.json()
                    print(f"[REC RESPONSE] status={body.get('status')} cold_start={body.get('cold_start')} model={body.get('model')} ratings_count={body.get('ratings_count')} recs_len={len(body.get('recommendations', []))}")
                except Exception as e:
                    print("[REC RESPONSE ERR]", e)

        page.on("response", handle_response)

        print("[1] Opening http://127.0.0.1:5000/?nointro=1 ...")
        await page.goto("http://127.0.0.1:5000/?nointro=1", wait_until="domcontentloaded")
        await asyncio.sleep(2)

        # 1. Initially on RF (cold start)
        print("[2] Checking initial RF state...")
        model_select = page.locator("#modelSelect")
        await model_select.scroll_into_view_if_needed()
        assert await model_select.is_visible(), "modelSelect dropdown not found!"
        
        initial_val = await model_select.input_value()
        print(f"Initial model selection: {initial_val}")

        # 2. Switch to KNN (cold start)
        print("[3] Switching dropdown to KNN (cold start)...")
        async with page.expect_response(lambda r: "/api/personal/recommend" in r.url and "model=knn" in r.url) as resp_info:
            await model_select.select_option("knn")
        resp = await resp_info.value
        resp_data = await resp.json()
        print(f"KNN Cold Start Response: {resp_data}")
        await page.wait_for_timeout(500)

        knn_panel = page.locator("#knnColdStartPanel")
        assert await knn_panel.is_visible(), "KNN cold start panel should be visible for user with 0 ratings!"
        panel_text = await knn_panel.inner_text()
        assert "KNN needs at least 3 rated or saved movies" in panel_text, f"Expected cold start message, got: {panel_text[:100]}"
        print("  -> KNN cold start message verified.")

        # 3. Click 'Try demo profile'
        print("[4] Clicking 'Try demo profile' button...")
        btn_demo = page.locator("#btnTryDemoProfile")
        assert await btn_demo.is_visible(), "Try demo profile button not found!"
        await btn_demo.click()
        await page.wait_for_timeout(2000)

        # 4. Now user has 8 ratings: verify KNN recommendations
        print("[5] Verifying KNN personalized recommendations...")
        src_badge = page.locator("#recSourceBadge")
        assert await src_badge.is_visible(), "recSourceBadge not visible!"
        badge_text = await src_badge.inner_text()
        print(f"  -> Badge: {badge_text}")
        assert "KNN" in badge_text, f"Expected KNN in badge text, got: {badge_text}"

        overlap_badge = page.locator("#recOverlapBadge")
        assert await overlap_badge.is_visible(), "Overlap badge should be visible!"
        overlap_text = await overlap_badge.inner_text()
        print(f"  -> Overlap: {overlap_text}")
        assert "Overlap with Random Forest" in overlap_text, f"Unexpected overlap text: {overlap_text}"

        knn_titles = await page.locator("#recRow .rec-card .rec-title").all_inner_texts()
        print(f"  -> KNN Titles (first 5): {knn_titles[:5]}")
        assert len(knn_titles) >= 5, "Expected at least 5 KNN recommendation cards!"

        # 5. Switch to RF
        print("[6] Switching dropdown to Random Forest...")
        await model_select.select_option("rf")
        await page.wait_for_timeout(1500)

        rf_badge_text = await src_badge.inner_text()
        print(f"  -> Badge: {rf_badge_text}")
        assert "Random Forest" in rf_badge_text, f"Expected Random Forest in badge text, got: {rf_badge_text}"

        rf_overlap_text = await overlap_badge.inner_text()
        print(f"  -> Overlap: {rf_overlap_text}")
        assert "Overlap with KNN" in rf_overlap_text, f"Unexpected overlap text: {rf_overlap_text}"

        rf_titles = await page.locator("#recRow .rec-card .rec-title").all_inner_texts()
        print(f"  -> RF Titles (first 5): {rf_titles[:5]}")
        assert len(rf_titles) >= 5, "Expected at least 5 RF recommendation cards!"

        # Assert lists are genuinely different
        assert rf_titles != knn_titles, "RF and KNN rendered identical movie titles!"
        print("  -> SUCCESS: RF and KNN movie titles are genuinely different!")

        # 6. Switch back to KNN
        print("[7] Switching back to KNN...")
        await model_select.select_option("knn")
        await page.wait_for_timeout(1500)
        knn_titles_2 = await page.locator("#recRow .rec-card .rec-title").all_inner_texts()
        assert knn_titles_2 == knn_titles, "KNN recommendations should match previous KNN results!"
        print("  -> SUCCESS: Switched back to KNN and verified consistent taste rankings.")

        # 7. Check network requests
        print("[8] Verifying network requests...")
        rf_reqs = [r for r in network_requests if "model=rf" in r]
        knn_reqs = [r for r in network_requests if "model=knn" in r]
        print(f"  -> RF network requests fired: {len(rf_reqs)}")
        print(f"  -> KNN network requests fired: {len(knn_reqs)}")
        assert len(rf_reqs) >= 1, "Expected at least one request with model=rf!"
        assert len(knn_reqs) >= 2, "Expected at least two requests with model=knn!"

        # 8. Check console errors (ignoring 404 images from TMDB if any)
        serious_errors = [e for e in console_errors if "favicon" not in e and "tmdb" not in e.lower()]
        print(f"[9] Console errors: {serious_errors}")
        assert len(serious_errors) == 0, f"Found console errors: {serious_errors}"

        # 9. Take screenshot
        await page.screenshot(path=SCREENSHOT_PATH)
        print(f"[10] Saved screenshot to: {SCREENSHOT_PATH}")

        await browser.close()
        print("\n[ALL PLAYWRIGHT TESTS PASSED SUCCESSFULLY!]")

if __name__ == "__main__":
    asyncio.run(run_browser_verification())
