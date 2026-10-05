import asyncio
import os
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

from scraper import get_chapter_title_and_download

# Muhit o'zgaruvchilarini .env faylidan o'qish
load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise ValueError("BOT_TOKEN is missing in environment variables. Please check your .env file.")

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class DownloadState(StatesGroup):
    waiting_for_url = State()
    waiting_for_filename_choice = State()
    waiting_for_custom_name = State()

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await message.answer(
        "Assalomu alaykum! Men Mangalab.uz saytidan mangalarni PDF qilib yuklab beruvchi botman.\n\n"
        "Menga shunchaki biror manganing bobi (glavasi) havolasini yuboring."
    )
    await state.set_state(DownloadState.waiting_for_url)

@dp.message(DownloadState.waiting_for_url, F.text.startswith("https://mangalab.uz/"))
async def process_url(message: Message, state: FSMContext):
    url = message.text
    await state.update_data(url=url)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Avtomatik (Sayt nomi bilan)", callback_data="name_auto")],
        [InlineKeyboardButton(text="O'zim nom kiritaman", callback_data="name_custom")]
    ])

    await message.answer("PDF fayl qanday nom bilan saqlansin?", reply_markup=keyboard)
    await state.set_state(DownloadState.waiting_for_filename_choice)

@dp.message(DownloadState.waiting_for_url)
async def process_invalid_url(message: Message):
    await message.answer("Iltimos, mangalab.uz saytidan to'g'ri havola yuboring.")

@dp.callback_query(DownloadState.waiting_for_filename_choice, F.data == "name_auto")
async def process_auto_name(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Avtomatik nom tanlandi. Yuklab olish boshlanmoqda... ⏳")
    data = await state.get_data()
    url = data.get("url")

    await state.set_state(DownloadState.waiting_for_url) # Ready for next url

    await process_download(callback.message, url, None)
    await callback.answer()

@dp.callback_query(DownloadState.waiting_for_filename_choice, F.data == "name_custom")
async def process_custom_name(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Iltimos, PDF fayl uchun nom kiriting:")
    await state.set_state(DownloadState.waiting_for_custom_name)
    await callback.answer()

@dp.message(DownloadState.waiting_for_custom_name)
async def process_custom_name_input(message: Message, state: FSMContext):
    custom_name = message.text.strip()
    if not custom_name.endswith('.pdf'):
        custom_name += '.pdf'

    data = await state.get_data()
    url = data.get("url")

    await state.set_state(DownloadState.waiting_for_url) # Ready for next url
    await message.answer(f"Fayl nomi `{custom_name}` qilib belgilandi. Yuklab olish boshlanmoqda... ⏳", parse_mode="Markdown")

    await process_download(message, url, custom_name)

async def process_download(message: Message, url: str, filename: str):
    msg = await message.answer("Rasmlar olinmoqda va PDF ga yig'ilmoqda. Iltimos kuting (bu jarayon sahifadagi rasmlar soniga qarab 1-2 daqiqa olishi mumkin)...")

    try:
        success, final_filename = await get_chapter_title_and_download(url, filename)

        if success and final_filename and os.path.exists(final_filename):
            await msg.edit_text("PDF tayyor! Yuborilmoqda... 🚀")

            # Send document
            document = FSInputFile(final_filename)
            await message.answer_document(document=document)

            # Faylni o'chirish
            try:
                os.remove(final_filename)
            except Exception as e:
                print(f"Faylni o'chirishda xatolik: {e}")

            await msg.delete()
        else:
            await msg.edit_text("Kechirasiz, ushbu havoladan rasmlarni yuklab olib bo'lmadi yoki xatolik yuz berdi. Sahifada rasmlar borligiga va havola to'g'riligiga ishonch hosil qiling.")

    except Exception as e:
        await msg.edit_text(f"Kutilmagan xatolik yuz berdi: {e}")

async def main():
    print("Bot ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
