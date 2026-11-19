"""
ui_smoke.py - Dual-Viewport Playwright UI Smoke Test Runner
Runs headless Chromium across Desktop (1400x900) and Mobile (390x844) viewports.
Checks for uncaught exceptions, network failures, element visibility, and saves screenshots.
"""
import os
import sys
import asyncio
from playwright.async_api import async_playwright

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_URL = "http://localhost:5000"
SCREENSHOTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests", "screenshots")
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

VIEWPORTS = [
    {"name": "Desktop (1400x900)", "width": 1400, "height": 900, "is_mobile": False},
    {"name": "Mobile (390x844)", "width": 390, "height": 844, "is_mobile": True}
]

PAGES = [
    {"path": "/?nointro=1", "name": "Homepage", "selector": "#hero"},
    {"path": "/watchlist", "name": "Watchlist", "selector": "#watchlistCount"},
    {"path": "/login", "name": "Login/Signup", "selector": "#tabSignIn"}
]

async def run_smoke():
    results = []
    print("\n" + "=" * 65)
    print(" CineStream Dual-Viewport UI Smoke Test Suite")
    print("=" * 65)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        for vp in VIEWPORTS:
            context = await browser.new_context(
                viewport={"width": vp["width"], "height": vp["height"]},
                is_mobile=vp["is_mobile"]
            )
            page = await context.new_page()

            for page_info in PAGES:
                url = f"{BASE_URL}{page_info['path']}"
                test_label = f"{page_info['name']} on {vp['name']}"
                errors = []
                page.on("pageerror", lambda err: errors.append(str(err)))

                try:
                    res = await page.goto(url, wait_until="networkidle", timeout=15000)
                    status_code = res.status if res else None
                    await page.wait_for_selector(page_info["selector"], timeout=8000)

                    # Save screenshot
                    shot_name = f"smoke_{page_info['name'].lower().replace('/', '_')}_{'mobile' if vp['is_mobile'] else 'desktop'}.png"
                    shot_path = os.path.join(SCREENSHOTS_DIR, shot_name)
                    await page.screenshot(path=shot_path)

                    passed = (status_code == 200) and (len(errors) == 0)
                    results.append({
                        "test": test_label,
                        "status": "PASS" if passed else "FAIL",
                        "code": status_code,
                        "errors": len(errors),
                        "screenshot": shot_name
                    })
                except Exception as ex:
                    results.append({
                        "test": test_label,
                        "status": "FAIL",
                        "code": "ERR",
                        "errors": str(ex),
                        "screenshot": "N/A"
                    })

            await context.close()

        await browser.close()

    print("\n" + "-" * 75)
    print(f"{'Test':<40} | {'Status':<8} | {'HTTP':<6} | {'Errors':<6}")
    print("-" * 75)
    all_passed = True
    for r in results:
        status_str = f"\033[92m{r['status']}\033[0m" if r["status"] == "PASS" else f"\033[91m{r['status']}\033[0m"
        print(f"{r['test']:<40} | {r['status']:<8} | {str(r['code']):<6} | {str(r['errors']):<6}")
        if r["status"] != "PASS":
            all_passed = False
    print("-" * 75)

    if all_passed:
        print("\n [SUCCESS] ALL UI SMOKE TESTS PASSED!")
    else:
        print("\n [WARNING] Some UI smoke tests failed.")
    return all_passed

if __name__ == "__main__":
    success = asyncio.run(run_smoke())
    sys.exit(0 if success else 1)
