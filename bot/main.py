import os
import logging
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ChatJoinRequestHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

from .handlers import (
    start, button_handler, grant_command, signal_command, join_request_handler, main_menu_text_handler, 
    start_signal_creation, get_signal_type, get_signal_price, get_signal_sl, get_signal_tp, get_signal_reason, cancel_handler,
    SIGNAL_TYPE, SIGNAL_PRICE, SIGNAL_SL, SIGNAL_TP, SIGNAL_REASON,
    db, engine
)

# Muhit o'zgaruvchilarini yuklash
load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Sozlamalar
TOKEN = os.getenv("BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID") # Maxfiy kanal ID si

# Dublikat signallarni oldini olish uchun holat
last_signal_info = db.get_last_signal_info()
last_signal_time = last_signal_info['time'] if last_signal_info else None
last_signal_type = last_signal_info['type'] if last_signal_info else None

async def check_market_job(context: ContextTypes.DEFAULT_TYPE):
    """
    Bozorni tekshirish va signallarni yuborish uchun rejalashtirilgan vazifa.
    """
    global last_signal_time, last_signal_type
    try:
        symbol = "XAU/USD"
        # StrategyEngine endi NewsFilter va COTAnalyzer ni o'z ichiga oladi
        signal = engine.check_signal(symbol)
        
        if signal:
            signal_time = signal['time']
            signal_type = signal['type']
            
            if last_signal_time == signal_time:
                return
            
            if last_signal_type == signal_type and last_signal_time:
                if not isinstance(last_signal_time, datetime):
                    try: last_signal_time = last_signal_time.to_pydatetime()
                    except: pass
                if datetime.utcnow() - last_signal_time < timedelta(hours=4):
                    logger.info(f"{signal_type} signali o'tkazib yuborildi (4 soatlik cooldown)")
                    return

            last_signal_time = signal_time
            last_signal_type = signal_type
            
            entry_price = float(signal['price'])
            sl_price = float(signal['sl'])
            tp_price = float(signal['tp'])
            
            sl_dist = abs(entry_price - sl_price)
            tp_dist = abs(tp_price - entry_price)
            rr_ratio = tp_dist / sl_dist if sl_dist != 0 else 0
            
            balance = 1000
            risk_percent = 0.01
            risk_amount = balance * risk_percent
            lot_size = risk_amount / (sl_dist * 100) if sl_dist != 0 else 0.01
            lot_size = max(0.01, round(lot_size, 2))
 
            try:
                dt = signal['time']
                if hasattr(dt, 'to_pydatetime'):
                    dt = dt.to_pydatetime()
                uz_time = dt + timedelta(hours=5)
                months = ["Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun", 
                          "Iyul", "Avgust", "Sentyabr", "Oktyabr", "Noyabr", "Dekabr"]
                m_name = months[uz_time.month-1]
                time_str = f"{uz_time.day}-{m_name}, {uz_time.strftime('%H:%M')}"
            except:
                time_str = str(signal['time'])

            # Ball tizimi (Sentiment Score)
            # Default ga 0 beramiz
            score = signal.get('score', 0)
            score_dots = "🟢" * score + "⚪" * (3 - score)
            strength_text = "🔥 KUCHLI" if score == 3 else "⚡️ O'RTA"

            # Kanal uchun xabar
            msg = (
                f"🔔 <b>GOLD (XAU/USD) SIGNAL</b> 🔔\n\n"
                f"Daraja: <b>{strength_text} ({score_dots})</b>\n"
                f"Yo'nalish: <b>{'🟢 BUY' if signal['type'] == 'BUY' else '🔴 SELL'}</b>\n"
                f"Kirish: <code>{entry_price:.2f}</code>\n\n"
                f"🛑 <b>Stop Loss:</b> <code>{sl_price:.2f}</code>\n"
                f"🎯 <b>Take Profit:</b> <code>{tp_price:.2f}</code>\n\n"
                f"📊 <b>Risk Management:</b>\n"
                f"• Lot: <b>{lot_size}</b> (Balans $1000)\n"
                f"• R/R Ratio: <b>1:{rr_ratio:.1f}</b>\n\n"
                f"📝 <b>Sabab:</b> {signal['reason']}\n"
            )

            # COT moduli haqida ma'lumot (agar bo'lsa)
            if 'cot_info' in signal and signal['cot_info']:
                cot = signal['cot_info']
                msg += f"🏦 <b>COT Index:</b> <code>{cot['cot_index']}%</code>\n"

            msg += f"⏰ <b>Vaqt:</b> <code>{time_str}</code>"
            
            signal_id = db.log_signal(
                symbol=signal['symbol'],
                signal_type=signal['type'],
                price=float(signal['price']),
                sl=float(signal['sl']),
                tp=float(signal['tp']),
                reason=signal['reason']
            )

            # Admin uchun kengaytirilgan xabar
            # Admin xabarida ham COT va boshqa yangi ma'lumotlar bo'lishi kerak
            admin_msg = (
                f"📝 <b>YANGI SIGNAL (TASDIQLASH)</b>\n\n"
                f"Daraja: {strength_text} ({score_dots})\n"
                f"Yo'nalish: <b>{signal['type']}</b>\n"
                f"Kirish: <code>{entry_price:.2f}</code>\n"
                f"🛑 SL: <code>{sl_price:.2f}</code> | 🎯 TP: <code>{tp_price:.2f}</code>\n\n"
                f"📝 Sabab: {signal['reason']}\n"
            )
            
            if 'cot_info' in signal and signal['cot_info']:
                cot = signal['cot_info']
                admin_msg += f"🏦 COT: {cot['net_change']}% o'zgargan, Index: {cot['cot_index']}%\n"
                
            admin_msg += f"\nKanalga chiqarilsinmi?"
            
            admin_kb = [
                [
                    InlineKeyboardButton("✅ Chiqarish", callback_data=f"sigpub_{signal_id}"),
                    InlineKeyboardButton("❌ Rad etish", callback_data=f"sigrej_{signal_id}")
                ]
            ]

            ADMIN_ID = "1032563269"
            try:
                await context.bot.send_message(
                    chat_id=ADMIN_ID, 
                    text=admin_msg, 
                    reply_markup=InlineKeyboardMarkup(admin_kb),
                    parse_mode='HTML'
                )
                logger.info(f"Signal {signal_id} tasdiqlash uchun adminga yuborildi.")
            except Exception as e:
                logger.error(f"Signalni adminga yuborishda xatolik: {e}")

    except Exception as e:
        logger.error(f"check_market_job da xatolik: {e}")

async def check_subscription_job(context: ContextTypes.DEFAULT_TYPE):
    expired_subs = db.get_expired_subscriptions()
    for sub in expired_subs:
        try:
            if CHANNEL_ID:
                await context.bot.ban_chat_member(chat_id=CHANNEL_ID, user_id=sub.user_id)
                await context.bot.unban_chat_member(chat_id=CHANNEL_ID, user_id=sub.user_id)
            await context.bot.send_message(
                chat_id=sub.user_id,
                text="⚠️ Sizning premium obunangiz muddati tugadi. Kanaldan chiqarildingiz.\n"
                     "Qayta a'zo bo'lish uchun /start bosing."
            )
            db.deactivate_subscription(sub.user_id)
            logger.info(f"Foydalanuvchi {sub.user_id} obunasi tugadi.")
        except Exception as e:
            logger.error(f"Foydalanuvchi {sub.user_id} ni chiqarishda xatolik: {e}")

    expiring_soon = db.get_expiring_soon_subscriptions(hours=24)
    for sub in expiring_soon:
        try:
            await context.bot.send_message(
                chat_id=sub.user_id,
                text="🔔 Eslatma: Sizning premium obunangiz 24 soatdan keyin tugaydi."
            )
        except: pass

def run_bot():
    if not TOKEN:
        print("Xatolik: .env faylida BOT_TOKEN topilmadi")
        return
    app = ApplicationBuilder().token(TOKEN).build()
    
    # Conversation Handler yaratish (RegEx updated for multi-language)
    signal_conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^(✍️ Signal Yozish|✍️ Сигнал)$"), start_signal_creation)],
        states={
            SIGNAL_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_signal_type)],
            SIGNAL_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_signal_price)],
            SIGNAL_SL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_signal_sl)],
            SIGNAL_TP: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_signal_tp)],
            SIGNAL_REASON: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_signal_reason)],
        },
        fallbacks=[MessageHandler(filters.Regex("^(Bekor qilish|Отмена)$"), cancel_handler)]
    )

    app.add_handler(signal_conv_handler)
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("grant", grant_command))
    app.add_handler(CommandHandler("signal", signal_command))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(ChatJoinRequestHandler(join_request_handler))
    
    # Asosiy menyu handlerini eng oxiriga qo'shamiz, chunki u barcha textlarga javob beradi
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, main_menu_text_handler))
    
    scheduler = app.job_queue
    scheduler.run_repeating(check_market_job, interval=20, first=10)
    scheduler.run_daily(check_subscription_job, time=datetime.now().time())
    print("Bot ishga tushdi...")
    app.run_polling()

if __name__ == "__main__":
    run_bot()
