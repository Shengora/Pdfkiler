import asyncio
import os
import re
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

from scraper import get_chapter_title_and_download

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError("BOT_TOKEN is missing in environment variables. Please check your .env file.")

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class DownloadState(StatesGroup):
    waiting_for_url = State()
    waiting_for_chapter_range = State()
    waiting_for_filename_choice = State()
    waiting_for_custom_name = State()

def parse_manga_url(url):
    # Mangalab format: .../bob/1/
    match_mangalab = re.search(r'(.*\/bob\/)(\d+)(\/.*)?', url)
    if match_mangalab:
        base_url = match_mangalab.group(1)
        current_chapter = int(match_mangalab.group(2))
        tail = match_mangalab.group(3) if match_mangalab.group(3) else "/"
        return base_url, current_chapter, tail

    # Mangabox format: .../read?titleId=xxx&episodeId=xxx__ch001&no=1
    match_mangabox = re.search(r'(.*__ch)(\d+)(&no=)(\d+)', url)
    if match_mangabox:
        base_url = match_mangabox.group(1)
        current_chapter = int(match_mangabox.group(4))
        return base_url, current_chapter, ""

    return None, None, None

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await message.answer(
        "Assalomu alaykum! Men Mangalab.uz va Mangabox.uz saytlaridan mangalarni PDF qilib yuklab beruvchi botman.\n\n"
        "Menga shunchaki biror manganing bobi (glavasi) havolasini yuboring."
    )
    await state.set_state(DownloadState.waiting_for_url)

@dp.message(DownloadState.waiting_for_url, (F.text.startswith("https://mangalab.uz/") | F.text.startswith("https://www.mangabox.uz/") | F.text.startswith("https://mangabox.uz/")))
async def process_url(message: Message, state: FSMContext):
    url = message.text
    base_url, chapter, tail = parse_manga_url(url)

    if not base_url:
        await message.answer("Siz yuborgan havolada bob (glava) raqami topilmadi. Iltimos aniq bob linkini yuboring (masalan .../bob/1/ yoki .../read?...).")
        return

    await state.update_data(url=url, base_url=base_url, tail=tail, original_chapter=chapter)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Faqat shu bobni yuklash", callback_data="range_single")],
        [InlineKeyboardButton(text="Bir nechta bobni yuklash", callback_data="range_multiple")]
    ])

    await message.answer(f"Siz {chapter}-bobni yubordingiz. Qanday yuklab olamiz?", reply_markup=keyboard)

@dp.message(DownloadState.waiting_for_url)
async def process_invalid_url(message: Message):
    await message.answer("Iltimos, mangalab.uz yoki mangabox.uz saytidan to'g'ri havola yuboring.")

@dp.callback_query(F.data == "range_single")
async def process_range_single(callback: CallbackQuery, state: FSMContext):
    await state.update_data(chapters="single")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Avtomatik (Sayt nomi bilan)", callback_data="name_auto")],
        [InlineKeyboardButton(text="O'zim nom kiritaman (Shablon)", callback_data="name_custom")]
    ])

    await callback.message.edit_text("PDF fayl qanday nom bilan saqlansin?", reply_markup=keyboard)
    await state.set_state(DownloadState.waiting_for_filename_choice)
    await callback.answer()

@dp.callback_query(F.data == "range_multiple")
async def process_range_multiple(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Qaysi oraliqdagi boblarni yuklamoqchisiz? \n"
        "Masalan: 1-5 yoki 10-15 shaklida raqamlarni yozib yuboring."
    )
    await state.set_state(DownloadState.waiting_for_chapter_range)
    await callback.answer()

@dp.message(DownloadState.waiting_for_chapter_range)
async def process_chapter_range_input(message: Message, state: FSMContext):
    text = message.text.strip()
    match = re.match(r'^(\d+)\s*-\s*(\d+)$', text)
    if not match:
        await message.answer("Iltimos, formatni to'g'ri kiriting. Masalan: 1-5")
        return

    start_ch = int(match.group(1))
    end_ch = int(match.group(2))

    if start_ch > end_ch:
        start_ch, end_ch = end_ch, start_ch

    if end_ch - start_ch > 20:
        await message.answer("Bir martada ko'pi bilan 20 ta bobni yuklab olish mumkin. Kichikroq oraliq kiriting.")
        return

    await state.update_data(chapters="multiple", start_ch=start_ch, end_ch=end_ch)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Avtomatik (Sayt nomi bilan)", callback_data="name_auto")],
        [InlineKeyboardButton(text="O'zim nom kiritaman (Shablon)", callback_data="name_custom")]
    ])

    await message.answer("PDF fayl qanday nom bilan saqlansin?", reply_markup=keyboard)
    await state.set_state(DownloadState.waiting_for_filename_choice)

@dp.callback_query(DownloadState.waiting_for_filename_choice, F.data == "name_auto")
async def process_auto_name(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Avtomatik nom tanlandi. Yuklab olish boshlanmoqda... ⏳")
    data = await state.get_data()
    await state.set_state(DownloadState.waiting_for_url)
    await process_downloads(callback.message, data, custom_name_template=None)
    await callback.answer()

@dp.callback_query(DownloadState.waiting_for_filename_choice, F.data == "name_custom")
async def process_custom_name(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "Iltimos, PDF fayl uchun nom kiriting.\n"
        "Masalan: `Jim Bo'l, Yovuz Ajdarho! @ManhwaGarden_Uz` \n"
        "Agar bir nechta bob yuklayotgan bo'lsangiz, men avtomatik ravishda boshiga `[00X]` raqamini qo'shib yuboraman."
    )
    await state.set_state(DownloadState.waiting_for_custom_name)
    await callback.answer()

@dp.message(DownloadState.waiting_for_custom_name)
async def process_custom_name_input(message: Message, state: FSMContext):
    custom_name = message.text.strip()
    data = await state.get_data()

    await message.answer(f"Fayl nomi tayyor. Yuklab olish boshlanmoqda... ⏳")
    await state.set_state(DownloadState.waiting_for_url)
    await process_downloads(message, data, custom_name_template=custom_name)

async def process_downloads(message: Message, data: dict, custom_name_template: str = None):
    chapters_type = data.get("chapters")

    if chapters_type == "single":
        url = data.get("url")
        chapter_num = data.get("original_chapter")
        filename = format_filename(custom_name_template, chapter_num, is_multiple=False)
        await download_and_send(message, url, filename, chapter_num=chapter_num)

    elif chapters_type == "multiple":
        base_url = data.get("base_url")
        tail = data.get("tail")
        start_ch = data.get("start_ch")
        end_ch = data.get("end_ch")

        await message.answer(f"Jami {end_ch - start_ch + 1} ta bob yuklab olinadi. Iltimos kuting...")

        for ch in range(start_ch, end_ch + 1):
            if "__ch" in base_url: # Mangabox logic
                url = f"{base_url}{ch:03d}&no={ch}"
            else: # Mangalab logic
                url = f"{base_url}{ch}{tail}"
            filename = format_filename(custom_name_template, ch, is_multiple=True)
            await download_and_send(message, url, filename, chapter_num=ch)

        await message.answer("Barcha belgilangan boblar yuklab bo'lindi! ✅")

def format_filename(template: str, chapter: int, is_multiple: bool):
    if not template:
        return None

    if template.lower().endswith('.pdf'):
        template = template[:-4]

    if is_multiple:
        return f"[{chapter:03d}] {template}.pdf"
    else:
        return f"{template}.pdf"

async def download_and_send(message: Message, url: str, filename: str, chapter_num: int = None):
    status_text = f"Yuklanmoqda: {chapter_num}-bob ⏳" if chapter_num else "Rasmlar olinmoqda va PDF ga yig'ilmoqda. Iltimos kuting (bu jarayon sahifadagi rasmlar soniga qarab 1-2 daqiqa olishi mumkin)..."
    msg = await message.answer(status_text)

    try:
        success, final_filename = await get_chapter_title_and_download(url, filename)

        if success and final_filename and os.path.exists(final_filename):
            await msg.edit_text(f"PDF tayyor! Yuborilmoqda... 🚀")

            document = FSInputFile(final_filename)
            await message.answer_document(document=document)

            try:
                os.remove(final_filename)
            except Exception as e:
                print(f"Faylni o'chirishda xatolik: {e}")

            await msg.delete()
        else:
            await msg.edit_text(f"Kechirasiz, ushbu havoladan rasmlarni yuklab olib bo'lmadi ({chapter_num}-bob).")

    except Exception as e:
        await msg.edit_text(f"Kutilmagan xatolik yuz berdi: {e}")

async def start_bot():
    print("Bot ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(start_bot())
