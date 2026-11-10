"""Drive the UI in headless Chrome: auto-play a caller demo, then capture the console.

    python scripts/screenshot_ui.py   (server must be running on :8930)
"""
import asyncio
import os
import sys
from pathlib import Path

from playwright.async_api import async_playwright

OUT = Path(__file__).resolve().parent.parent / "docs" / "screens"
BASE = "http://127.0.0.1:8930"


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

        await page.goto(BASE + "/")
        await page.wait_for_timeout(500)
        await page.screenshot(path=str(OUT / "1_overview.png"), full_page=True)

        await page.goto(BASE + "/caller.html")
        await page.uncheck("#voiceOn")
        idx = int(sys.argv[1]) if len(sys.argv) > 1 else 0
        await page.select_option("#scenario", index=idx)
        await page.click("#autoBtn")
        await page.wait_for_selector("text=Call complete", timeout=60000)
        await page.wait_for_timeout(400)
        await page.screenshot(path=str(OUT / "2_caller.png"), full_page=False)

        await page.goto(BASE + "/login.html")
        await page.fill("#u", "admin")
        await page.fill("#p", os.environ.get("SAATHI_ADMIN_PASSWORD", ""))
        await page.click("button[type=submit]")
        await page.wait_for_url("**/console.html")
        await page.wait_for_timeout(800)
        await page.click("#seedBtn")
        await page.wait_for_timeout(1500)
        await page.screenshot(path=str(OUT / "3_console.png"), full_page=False)
        await page.click(".tab[data-t=audit]")
        await page.wait_for_timeout(300)
        await page.screenshot(path=str(OUT / "4_console_audit.png"), full_page=False)
        await browser.close()
        print("errors:", errors)


asyncio.run(main())
