#!/usr/bin/env python3
"""
Test Playwright screenshot capability.
Usage: python scripts/test_screenshot.py <url> [output.png]

Examples:
  python scripts/test_screenshot.py http://192.168.1.1
  python scripts/test_screenshot.py http://10.0.0.1:8080 /tmp/router.png
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def take_screenshot(url: str, output: str = "test_screenshot.png"):
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("Playwright not installed. Run: pip install playwright && playwright install chromium")
        sys.exit(1)

    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            ignore_https_errors=True,
        )
        page = await context.new_page()
        try:
            print(f"Navigating to {url}...")
            await page.goto(url, timeout=8000, wait_until="networkidle")
            print(f"Final URL: {page.url}")
            await page.screenshot(path=output, full_page=False)
            print(f"Screenshot saved to {output}")
        except Exception as e:
            print(f"Failed: {e}")
            sys.exit(1)
        finally:
            await browser.close()


if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "http://example.com"
    out = sys.argv[2] if len(sys.argv) > 2 else "test_screenshot.png"
    asyncio.run(take_screenshot(url, out))
