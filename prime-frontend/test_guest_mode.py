import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        # Go to login page
        await page.goto('http://localhost:5173/login')
        
        # Click the guest button
        await page.click('#btn-guest-access')
        
        # Wait for navigation to app
        await page.wait_for_url('**/app*')
        
        # Wait for the guest banner to be visible
        try:
            await page.wait_for_selector('text="Modo Invitado — Los datos no se guardarán al cerrar sesión."', timeout=5000)
            print("SUCCESS: Appeared on /app with Guest Banner!")
            
            # Check for guest badge
            content = await page.content()
            if "👤 Invitado" in content:
                print("SUCCESS: Guest badge found!")
            else:
                print("FAIL: Guest badge not found.")
                
        except Exception as e:
            print("FAIL: Guest banner not found on the page or timeout.", e)
            print("Current URL:", page.url)
            
        await browser.close()

asyncio.run(run())
