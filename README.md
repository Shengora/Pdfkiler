# Mangalab PDF Bot

Bu Telegram bot Mangalab.uz saytidagi manga boblarini (glavalarini) yuklab olib, ularni bitta sifatli PDF fayl qilib foydalanuvchiga yuboradi.

## O'rnatish (Installation)

1. Kerakli paketlarni o'rnatish:
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   playwright install-deps chromium
   ```

2. `.env` faylini yaratish va sozlash:
   `.env.example` faylidan nusxa olib `.env` nomli fayl yarating va uning ichiga o'z botingiz tokenini kiriting:
   ```env
   BOT_TOKEN=123456789:AAH...
   ```

3. Botni ishga tushirish:
   ```bash
   python main.py
   ```

## Ishlatish

Botga mangalab.uz dagi biror bob havolasini yuboring. Masalan:
`https://mangalab.uz/manga-nomi/tarjimon/TarjimonNomi/jild/1/bob/1/`

Bot sizdan PDF nomini qanday saqlashni so'raydi. Siz sahifaning original nomi ("Sayt nomi bilan") yoxud o'zingiz kiritadigan maxsus nomni tanlashingiz mumkin.
