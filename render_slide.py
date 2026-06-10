import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

SLIDE = Path("site/before-after-slide.html").resolve()

async def main():
    url = SLIDE.as_uri()
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        pg = await b.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=2)
        await pg.goto(url, wait_until="networkidle")
        el = await pg.query_selector(".slide")
        await el.screenshot(path="site/before-after-slide.png")
        await pg.pdf(path="site/before-after-slide.pdf", width="1280px", height="720px", print_background=True)
        await b.close()
    print("rendered PNG + PDF")

asyncio.run(main())
