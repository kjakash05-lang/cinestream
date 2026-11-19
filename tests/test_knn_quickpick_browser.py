"""
tests/test_knn_quickpick_browser.py
Playwright browser verification for KNN taste-profile quick-picks:
- Verifies exact 1 panel in DOM (no duplicate renders)
- Verifies all 5 cards display matching titles and valid posters (naturalWidth > 0)
- Verifies data-tmdb-id attributes
- Saves screenshot to tests/screenshots/knn_quickpick.png
"""
import os
import sys
import pytest
from playwright.sync_api import sync_playwright

def test_knn_quick_pick_browser():
    os.makedirs("tests/screenshots", exist_ok=True)
    screenshot_path = os.path.abspath("tests/screenshots/knn_quickpick.png")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        console_errors = []
        page.on("console", lambda msg: print(f"[Browser {msg.type}] {msg.text}"))
        page.on("pageerror", lambda err: print(f"[PageError] {err}"))

        print("\nNavigating to CineStream homepage...")
        page.goto("http://127.0.0.1:5000/?nointro=1", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)

        # Switch Model to KNN
        print("Selecting KNN model in dropdown...")
        page.select_option("#modelSelect", "knn")

        # Wait for KNN Cold Start Panel and cards to be dynamically rendered
        print("Waiting for #knnColdStartPanel to render...")
        page.wait_for_selector("#knnColdStartPanel .quick-rate-card", state="visible", timeout=25000)

        # Verify exactly ONE #knnColdStartPanel exists in the DOM
        panels = page.query_selector_all("#knnColdStartPanel")
        assert len(panels) == 1, f"Expected exactly 1 #knnColdStartPanel in DOM, found {len(panels)}"
        panel = panels[0]
        assert panel.is_visible(), "KNN Cold Start Panel should be visible"

        # Scroll to panel and let images load
        panel.scroll_into_view_if_needed()
        page.wait_for_timeout(2000)

        # Verify quick rate cards
        cards = page.query_selector_all(".quick-rate-card")
        print(f"Found {len(cards)} quick-rate cards")
        assert len(cards) == 5, f"Expected 5 quick-rate cards, found {len(cards)}"

        expected_ids = {
            157336: ("Interstellar", "Hollywood"),
            656908: ("Ramayana", "Bollywood"),
            587412: ("K.G.F", "Sandalwood"),
            743563: ("Vikram", "Kollywood"),
            579974: ("RRR", "Tollywood")
        }

        for idx, card in enumerate(cards):
            card.scroll_into_view_if_needed()
            tmdb_id_str = card.get_attribute("data-tmdb-id")
            assert tmdb_id_str is not None, f"Card {idx} missing data-tmdb-id"
            tmdb_id = int(tmdb_id_str)
            assert tmdb_id in expected_ids, f"Unexpected tmdb_id {tmdb_id}"

            expected_title_part, expected_industry = expected_ids[tmdb_id]
            title_el = card.query_selector(".quick-rate-title")
            badge_el = card.query_selector(".quick-rate-badge")
            assert title_el is not None
            assert badge_el is not None

            title_text = title_el.inner_text()
            badge_text = badge_el.inner_text()

            assert expected_title_part.lower() in title_text.lower(), f"Card {tmdb_id} title mismatch: {title_text}"
            assert expected_industry.lower() in badge_text.lower(), f"Card {tmdb_id} badge mismatch: {badge_text}"

            img = card.query_selector("img.quick-rate-img")
            assert img is not None, f"Card {tmdb_id} missing img element"
            
            # Remove loading="lazy" so headless browser fetches immediately
            img.evaluate("el => el.removeAttribute('loading')")
            
            # Wait for image to load
            page.wait_for_function("el => el.complete && el.naturalWidth > 0", arg=img, timeout=15000)
            natural_width = img.evaluate("el => el.naturalWidth")
            print(f"Card [{title_text}] ({badge_text}) -> TMDB ID: {tmdb_id}, img naturalWidth: {natural_width}")
            assert natural_width > 0, f"Image for {title_text} failed to load (naturalWidth={natural_width})"

        page.screenshot(path=screenshot_path)
        print(f"Saved screenshot to {screenshot_path}")

        browser.close()

    assert os.path.exists(screenshot_path)
    print("ALL KNN QUICK-PICK BROWSER CHECKS PASSED!")

if __name__ == "__main__":
    test_knn_quick_pick_browser()
