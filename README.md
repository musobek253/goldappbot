# Gold Trading Bot (XAU/USD) 🤖📈

Ushbu bot Forex bozorida XAU/USD (Oltin) juftligi uchun avtomatik signallar berish va tahlil qilish uchun ishlab chiqilgan.

## Asosiy Xususiyatlar 🌟

*   **Avtomatik Signallar:** RSI, EMA va boshqa indikatorlar asosida BUY/SELL signallari.
*   **COT Tahlili:** "Smart Money" (Hedge Funds) pozitsiyalari bo'yicha fundamental tahlil.
*   **Yangiliklar Filtri:** Muhim iqtisodiy yangiliklar (High Impact News) vaqtida savdoni to'xtatish.
*   **Risk Menejment:** Avtomatik Lot size va Risk/Reward (R/R) hisoblash.
*   **Admin Panel:** 
    *   Qo'lda signal yuborish (Wizard rejimi).
    *   Obunalarni boshqarish (Haftalik/Oylik).
    *   Foydalanuvchi to'lovlarini tasdiqlash.
*   **Multilingual:** O'zbek va Rus tillarini qo'llab-quvvatlash.

## O'rnatish va Ishga Tushirish 🛠

### 1. Talablar
*   Python 3.9+
*   Telegram Bot Token (BotFather dan)
*   VPS yoki Server (Ubuntu tavsiya etiladi)

### 2. O'rnatish

Repozitoriyani yuklab oling:
```bash
git clone https://github.com/musobek253/goldappbot.git
cd goldappbot
```

Virtual muhit yarating va aktivlashtiring:
```bash
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

Kutubxonalarni o'rnating:
```bash
pip install -r requirements.txt
```

### 3. Sozlash (.env)

`.env` faylini yarating va quyidagi ma'lumotlarni kiriting:
```bash
BOT_TOKEN=YOUR_BOT_TOKEN
CHANNEL_ID=YOUR_CHANNEL_ID # Signallar chiqadigan kanal ID si
GOLDAPI_KEY=YOUR_GOLDAPI_KEY # (Ixtiyoriy)
```

### 4. Ishga tushirish

```bash
python main.py
```

## Admin Buyruqlari 👨‍💻

*   `/start` - Botni ishga tushirish.
*   `/grant [user_id] [kun]` - Foydalanuvchiga tekin obuna berish.
*   `/signal` - (Eski) Qo'lda signal yuborish.
*   **Menyu orqali:** "✍️ Signal Yozish" tugmasi orqali qulay signal yuborish mumkin.

## Loyiha Tuzilishi imb
*   `bot/` - Telegram bot logikasi va handleri.
*   `strategies/` - Savdo strategiyalari, COT va Yangiliklar filtri.
*   `db/` - SQLite baza bilan ishlash.
*   `data/` - Narxlar va kalendar ma'lumotlari.

---
**Muallif:** @musoqudratov
