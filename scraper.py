import asyncio
import io
import os
import re
from PIL import Image
from playwright.async_api import async_playwright

async def get_chapter_title_and_download(url: str, output_filename: str):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)

            # Sahifa nomini olish (Manga nomi va bob raqami)
            try:
                page_title = await page.title()
                # "Qahramon qissasi - Bob 4 | MangaLab.uz" -> "Qahramon qissasi - Bob 4"
                clean_title = page_title.split('|')[0].strip()
                # Remove invalid characters for filename
                clean_title = re.sub(r'[\\/*?:"<>|]', "", clean_title)
            except:
                clean_title = "manga_chapter"

            if not clean_title:
                clean_title = "manga_chapter"


            await page.wait_for_timeout(3000)

            # Remove adblock modals, header/footer and sticky elements
            await page.evaluate('''() => {
                // Hide header/nav immediately if possible
                const headers = document.querySelectorAll('header, nav, .header, .nav, .navbar, .sticky-top');
                headers.forEach(h => h.style.display = 'none');

                const allElements = document.querySelectorAll('*');
                for (let el of allElements) {
                    const style = window.getComputedStyle(el);
                    if (style.position === 'fixed' || style.position === 'sticky') {
                        el.style.display = 'none';
                    }
                    if (style.zIndex > 100 && style.position === 'absolute') {
                        el.style.display = 'none';
                    }
                }

                // Specific text checks for adblock modals
                const textElements = document.querySelectorAll('div, section, article, p, h1, h2, h3, h4, h5');
                for (let el of textElements) {
                    const text = el.innerText ? el.innerText.toLowerCase() : '';
                    if (text.includes("adblock'ni o'chiring") || text.includes('adblock') || text.includes('reklama')) {
                        // Find the containing modal and hide it (assuming it's relatively small)
                        if (el.innerText.length < 1000) {
                            // try to hide parent nodes until we hit body
                            let parent = el;
                            while(parent && parent.tagName !== 'BODY') {
                                const style = window.getComputedStyle(parent);
                                if (style.position === 'fixed' || style.position === 'absolute' || parent.classList.contains('modal') || parent.classList.contains('popup')) {
                                    parent.style.display = 'none';
                                    break;
                                }
                                parent = parent.parentElement;
                            }
                            // also hide the element itself just in case
                            el.style.display = 'none';
                        }
                    }
                }
            }''')

            # Skrolling
            last_height = await page.evaluate("document.body.scrollHeight")
            while True:
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(2000)
                new_height = await page.evaluate("document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height


            # Elementlarni topish
            image_elements = await page.query_selector_all('img[src*="cdn.mangalab.uz/reader"], img[data-src*="cdn.mangalab.uz/reader"], .reading-content img, .page-break img, .wp-manga-chapter-img')

            if not image_elements:
                return False, None

            downloaded_images = []
            for i, img_el in enumerate(image_elements):
                try:
                    await img_el.scroll_into_view_if_needed()
                    await page.wait_for_timeout(500)

                    is_loaded = await img_el.evaluate("el => el.complete && el.naturalWidth !== 0")
                    if not is_loaded:
                        await page.wait_for_timeout(2000)

                    image_bytes = await img_el.screenshot()

                    img = Image.open(io.BytesIO(image_bytes))
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    downloaded_images.append(img)
                except Exception as e:
                    print(f"Error screenshotting image {i}: {e}")

            if not downloaded_images:
                return False, None

            if output_filename is None:
                output_filename = f"{clean_title}.pdf"

            downloaded_images[0].save(
                output_filename,
                save_all=True,
                append_images=downloaded_images[1:],
                resolution=100.0,
            )
            return True, output_filename

        except Exception as e:
            print(f"Error: {e}")
            return False, None
        finally:
            await browser.close()
