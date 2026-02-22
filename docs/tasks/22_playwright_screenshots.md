# Task 22: Playwright Setup for Web Screenshots

**Depends on:** Task 01, Task 14  
**Complexity:** Low  
**Description:** Install and configure Playwright (Chromium) for headless web screenshots during scans. Includes system dependencies, browser installation, and a standalone test script.

---

## Installation

```bash
# Activate venv
source /home/matheau/code/port_scan/venv/bin/activate

# Install playwright Python package (already in requirements from Task 01)
pip install playwright

# Install Chromium browser + system deps
playwright install chromium
playwright install-deps chromium
```

> **Note:** `playwright install-deps` requires root. Run as:
> ```bash
> sudo /home/matheau/code/port_scan/venv/bin/playwright install-deps chromium
> ```

---

## System Dependencies (Debian/Ubuntu)

If `install-deps` fails or is unavailable:

```bash
sudo apt-get install -y \
  libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
  libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
  libxfixes3 libxrandr2 libgbm1 libasound2 \
  libpango-1.0-0 libcairo2 libx11-xcb1
```

---

## Screenshot Directory

```bash
mkdir -p /home/matheau/code/port_scan/screenshots
chown netscan:netscan /home/matheau/code/port_scan/screenshots
chmod 750 /home/matheau/code/port_scan/screenshots
```

---

## `config.py` Addition

```python
# Add to config.py
SCREENSHOT_DIR: str = "/home/matheau/code/port_scan/screenshots"
SCREENSHOT_TIMEOUT_MS: int = 8000   # 8 seconds per page
```

---

## Standalone Test Script

`scripts/test_screenshot.py`:

```python
#!/usr/bin/env python3
"""
Test Playwright screenshot capability.
Usage: python scripts/test_screenshot.py <url> [output.png]
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def take_screenshot(url: str, output: str = "test_screenshot.png"):
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        page = await browser.new_page(viewport={"width": 1280, "height": 800})
        try:
            print(f"Navigating to {url}…")
            await page.goto(url, timeout=8000, wait_until="domcontentloaded")
            await page.screenshot(path=output, full_page=False)
            print(f"Screenshot saved to {output}")
        except Exception as e:
            print(f"Failed: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    url = sys.argv[1] if len(sys.argv) > 1 else "http://example.com"
    out = sys.argv[2] if len(sys.argv) > 2 else "test_screenshot.png"
    asyncio.run(take_screenshot(url, out))
```

```bash
# Test
python scripts/test_screenshot.py http://192.168.1.1 /tmp/router_screenshot.png
```

---

## Worker Integration Notes

The `tier5_screenshots` function in `worker/pipeline.py` (Task 14) uses:

```python
async with async_playwright() as p:
    browser = await p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
```

Key flags:
- `--no-sandbox` — required when running as a non-root system user
- `--disable-dev-shm-usage` — prevents crashes in low-memory environments

---

## Screenshot Filename Convention

```
{ip_address}_{port}.png
```

Examples:
- `192.168.1.1_80.png`
- `10.0.0.5_8443.png`

Stored in `/home/matheau/code/port_scan/screenshots/` and served via:
- FastAPI: `GET /api/hosts/screenshots/{filename}` (auth-gated)
- Nginx: `GET /screenshots/{filename}` (network-restricted, optional)

---

## Disabling Screenshots Per Profile

Screenshots are controlled by the `enable_screenshots` flag on each `ScanProfile`. If `False`, `tier5_screenshots` is skipped entirely in the worker pipeline.
