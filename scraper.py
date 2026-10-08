import asyncio
import io
import os
import re
from urllib.parse import urljoin
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

            # Smooth scrolling to trigger lazy loading for all images
            last_height = await page.evaluate("document.body.scrollHeight")
            stagnant_count = 0
            scroll_attempts = 0
            max_scroll_attempts = 300 # Increased limit to handle very long manga chapters

            while scroll_attempts < max_scroll_attempts:
                scroll_attempts += 1
                # Scroll down by viewport height
                await page.evaluate("window.scrollBy(0, window.innerHeight)")
                await page.wait_for_timeout(500)

                # Also check if we reached the bottom
                current_scroll = await page.evaluate("window.scrollY + window.innerHeight")
                current_height = await page.evaluate("document.body.scrollHeight")

                if current_height > last_height:
                    last_height = current_height
                    stagnant_count = 0
                elif current_scroll >= current_height - 10: # Reached bottom
                    stagnant_count += 1

                if stagnant_count >= 5: # Give it some time if it just reached bottom
                    break

            # Elementlarni topish
            image_elements = await page.query_selector_all('img[src*="cdn.mangalab.uz/reader"], img[data-src*="cdn.mangalab.uz/reader"], .reading-content img, .page-break img, .wp-manga-chapter-img, img[src*="cdn.mangabox.uz"]')

            if not image_elements:
                print("No image elements found with selector")
                return False, None

            print(f"Found {len(image_elements)} image elements")

            # Extract URLs first
            image_urls = []
            for img_el in image_elements:
                src = await img_el.get_attribute('data-src') or await img_el.get_attribute('src')
                if not src:
                    continue
                if src.startswith('//'):
                    src = 'https:' + src
                elif src.startswith('/'):
                    src = urljoin(page.url, src)
                image_urls.append(src)

            downloaded_images = []

            # Helper function for async download
            async def download_image(url: str, index: int):
                try:
                    response = await context.request.get(url, headers={"Referer": page.url}, timeout=15000)
                    if response.ok:
                        image_bytes = await response.body()
                        img = Image.open(io.BytesIO(image_bytes))
                        if img.mode != 'RGB':
                            img = img.convert('RGB')
                        return index, img
                    else:
                        print(f"Error fetching image {index}: Status {response.status}")
                        return index, None
                except Exception as e:
                    print(f"Error downloading image {index}: {e}")
                    return index, None

            # Download images concurrently in batches
            batch_size = 5
            results = []
            for i in range(0, len(image_urls), batch_size):
                batch = image_urls[i:i+batch_size]
                tasks = [download_image(url, i + j) for j, url in enumerate(batch)]
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                for res in batch_results:
                    if isinstance(res, tuple) and res[1] is not None:
                        results.append(res)

            # Sort by index to maintain order
            results.sort(key=lambda x: x[0])
            downloaded_images = [img for _, img in results]

            if not downloaded_images:
                print("No downloaded images to save")
                return False, None

            # Find the maximum width among all images
            max_width = max(img.width for img in downloaded_images)

            # Resize images to match the maximum width while preserving aspect ratio
            resized_images = []
            for img in downloaded_images:
                if img.width != max_width:
                    # Calculate new height preserving aspect ratio
                    new_height = int((max_width / img.width) * img.height)
                    # Use Resampling.LANCZOS for high-quality downsampling/upsampling
                    resized_img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
                    resized_images.append(resized_img)
                else:
                    resized_images.append(img)

            if output_filename is None:
                output_filename = f"{clean_title}.pdf"

            resized_images[0].save(
                output_filename,
                save_all=True,
                append_images=resized_images[1:],
                resolution=100.0,
            )
            return True, output_filename

        except Exception as e:
            print(f"Error: {e}")
            return False, None
        finally:
            await browser.close()
