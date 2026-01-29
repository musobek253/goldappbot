import logging
import os
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes, ConversationHandler, CommandHandler, MessageHandler, filters
from db.database import Database
from strategies.engine import StrategyEngine
from data.feed import DataHandler
from bot.languages import TEXTS

logger = logging.getLogger(__name__)

# Singleton'larni ishga tushirish
db = Database()
data_handler = DataHandler()
engine = StrategyEngine(db, data_handler)

# States for manual signal conversation
SIGNAL_TYPE, SIGNAL_PRICE, SIGNAL_SL, SIGNAL_TP, SIGNAL_REASON = range(5)

ADMIN_ID = "1032563269"

def get_text(chat_id, key, **kwargs):
    lang = db.get_user_language(chat_id)
    text = TEXTS.get(lang, TEXTS['uz']).get(key, "")
    if kwargs:
        return text.format(**kwargs)
    return text

def get_main_keyboard(chat_id):
    lang = db.get_user_language(chat_id)
    t = TEXTS[lang]
    keyboard = [
        [KeyboardButton(t['tariffs_btn']), KeyboardButton(t['profile_btn'])],
        [KeyboardButton(t['status_btn']), KeyboardButton(t['news_btn'])],
        [KeyboardButton(t['settings_btn'])]
    ]
    if str(chat_id) == ADMIN_ID:
        keyboard.append([KeyboardButton(t['signal_btn'])])
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    db.add_subscriber(chat_id)
    
    msg = get_text(chat_id, 'welcome')
    reply_markup = get_main_keyboard(chat_id)
    
    await update.message.reply_text(msg, reply_markup=reply_markup)

async def main_menu_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text
    lang = db.get_user_language(chat_id)
    t = TEXTS[lang]

    # Handle language agnostic or check against current language texts
    
    if text == t['tariffs_btn']:
        keyboard = [
            [InlineKeyboardButton(t['week_10'], callback_data='sub_weekly')],
            [InlineKeyboardButton(t['month_30'], callback_data='sub_monthly')],
            [InlineKeyboardButton(t['back'], callback_data='back_main')]
        ]
        await update.message.reply_text(
            t['choose_tariff'],
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
    elif text == t['profile_btn']:
        user_id = update.effective_user.id
        sub = db.get_subscription(user_id)
        if sub and sub.is_active:
            status = t['profile_active']
            expiry = sub.end_date.strftime("%Y-%m-%d")
        else:
            status = t['profile_inactive']
            expiry = "-"
        
        msg = get_text(chat_id, 'profile_info', user_id=user_id, status=status, expiry=expiry)
        await update.message.reply_text(msg, parse_mode='HTML')
        
    elif text == t['status_btn']:
        price = data_handler.get_current_price("XAU/USD", force_fetch=True)
        now = datetime.now() + timedelta(hours=5)
        msg = get_text(chat_id, 'market_status', price=price, time=now.strftime('%H:%M:%S'))
        await update.message.reply_text(msg, parse_mode='HTML')
        
    elif text == t['news_btn']:
        upcoming = engine.news_filter.get_upcoming_news(hours=24)
        if not upcoming:
            msg = t['no_news']
        else:
            msg = t['news_header']
            for event in upcoming:
                msg += f"🕒 <b>{event['time']}</b> - {event['title']} ({event['impact']})\n"
            msg += "\n<i>Vaqtlar 2026 yil bo'yicha.</i>" # Hardcoded year for now/context
        
        await update.message.reply_text(msg, parse_mode='HTML')
        
    elif text == t['settings_btn']:
        keyboard = [
            [
                InlineKeyboardButton(t['lang_uz'], callback_data='lang_uz'),
                InlineKeyboardButton(t['lang_ru'], callback_data='lang_ru')
            ],
            [InlineKeyboardButton(t['help_btn'], callback_data='help')]
        ]
        await update.message.reply_text(
            t['settings_menu'],
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat_id
    lang = db.get_user_language(chat_id)
    t = TEXTS[lang]
    
    if query.data == 'tariffs':
        keyboard = [
            [InlineKeyboardButton(t['week_10'], callback_data='sub_weekly')],
            [InlineKeyboardButton(t['month_30'], callback_data='sub_monthly')],
            [InlineKeyboardButton(t['back'], callback_data='back_main')]
        ]
        await query.edit_message_text(
            t['choose_tariff'],
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )

    elif query.data in ['sub_weekly', 'sub_monthly']:
        price = "$10" if query.data == 'sub_weekly' else "$30"
        duration = "1 Hafta" if lang == 'uz' else "1 Неделя" # Hardcoded slightly for logic logic
        if query.data == 'sub_weekly':
             duration = "1 Hafta" if lang == 'uz' else "1 Неделя"
             days = 7
        else:
             duration = "1 Oy" if lang == 'uz' else "1 Месяц"
             days = 30
        
        user = query.from_user
        username = f"@{user.username}" if user.username else user.first_name
        
        msg = get_text(chat_id, 'payment_info', duration=duration, price=price)
        
        await query.edit_message_text(
            msg,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t['back'], callback_data='tariffs')]]),
            parse_mode='HTML'
        )
        
        admin_msg = f"🔔 <b>Yangi To'lov So'rovi!</b>\n\nFoydalanuvchi: {username}\nID: <code>{user.id}</code>\nTarif: {duration} ({price})"
        admin_kb = [[InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"approve_{user.id}_{days}"),
                     InlineKeyboardButton("❌ Rad etish", callback_data=f"reject_{user.id}")]]
        try:
            await context.bot.send_message(chat_id=ADMIN_ID, text=admin_msg, reply_markup=InlineKeyboardMarkup(admin_kb), parse_mode='HTML')
        except Exception as e:
            logger.error(f"Error: {e}")

    # Language Switch Handlers
    elif query.data == 'lang_uz':
        db.set_user_language(chat_id, 'uz')
        # Refresh text variable
        t = TEXTS['uz']
        await query.delete_message()
        await context.bot.send_message(
            chat_id=chat_id,
            text=t['lang_changed'],
            reply_markup=get_main_keyboard(chat_id)
        )
        
    elif query.data == 'lang_ru':
        db.set_user_language(chat_id, 'ru')
        t = TEXTS['ru']
        await query.delete_message()
        await context.bot.send_message(
            chat_id=chat_id,
            text=t['lang_changed'],
            reply_markup=get_main_keyboard(chat_id)
        )

    elif query.data == 'help':
        await query.edit_message_text(
            t['help_text'],
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t['back'], callback_data='back_settings')]]),
            parse_mode='HTML'
        )
        
    elif query.data == 'back_settings':
         keyboard = [
            [
                InlineKeyboardButton(t['lang_uz'], callback_data='lang_uz'),
                InlineKeyboardButton(t['lang_ru'], callback_data='lang_ru')
            ],
            [InlineKeyboardButton(t['help_btn'], callback_data='help')]
        ]
         await query.edit_message_text(
            t['settings_menu'],
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )

    elif query.data.startswith('approve_'):
        _, user_id, days = query.data.split('_')
        end_date = db.grant_subscription(user_id, int(days))
        await query.edit_message_text(text=f"{query.message.text_html}\n\n✅ <b>Tasdiqlandi!</b>", parse_mode='HTML')
        
        # Notify user in their language
        user_lang = db.get_user_language(user_id)
        u_t = TEXTS[user_lang]
        channel_link = 'https://t.me/+X49fsjSV6Ow2YmMy'
        
        msg = u_t['sub_approved'].format(days=days, date=end_date.strftime('%Y-%m-%d %H:%M'), link=channel_link)
        
        try:
            await context.bot.send_message(chat_id=user_id, text=msg, parse_mode='HTML')
        except: pass

    elif query.data.startswith('reject_'):
        _, user_id = query.data.split('_')
        await query.edit_message_text(text=f"{query.message.text_html}\n\n❌ <b>Rad etildi.</b>", parse_mode='HTML')
        try:
             user_lang = db.get_user_language(user_id)
             u_t = TEXTS[user_lang]
             await context.bot.send_message(chat_id=user_id, text=u_t['sub_rejected'])
        except: pass

    elif query.data.startswith('sigpub_'):
        signal_id = int(query.data.split('_')[1])
        signal_db = db.get_signal_by_id(signal_id)
        
        if signal_db:
            # Kanaldagi xabar - Kanal odatda bitta tilda bo'ladi, lekin biz umumiy formatda yozdik
            # Aslida kanal uchun til userga bog'liq emas. Kanal tili hardcode qilinishi mumkin yoki mixed.
            # Hozircha o'zbek tilida qoldiramiz kanal uchun, chunki kanal O'zbekistonda.
            
            # Lot hisoblash
            sl_dist = abs(signal_db.price - signal_db.sl)
            tp_dist = abs(signal_db.tp - signal_db.price)
            rr_ratio = tp_dist / sl_dist if sl_dist != 0 else 0
            lot_size = 10 / (sl_dist * 100) if sl_dist != 0 else 0.01
            lot_size = max(0.01, round(lot_size, 2))
            
            uz_time = signal_db.timestamp + timedelta(hours=5)
            months = ["Yanvar", "Fevral", "Mart", "Aprel", "May", "Iyun", "Iyul", "Avgust", "Sentyabr", "Oktyabr", "Noyabr", "Dekabr"]
            time_str = f"{uz_time.day}-{months[uz_time.month-1]}, {uz_time.strftime('%H:%M')}"

            channel_msg = (
                f"🔔 <b>GOLD (XAU/USD) SIGNAL</b> 🔔\n\n"
                f"Yo'nalish: <b>{'🟢 BUY' if signal_db.signal_type == 'BUY' else '🔴 SELL'}</b>\n"
                f"Kirish: <code>{signal_db.price:.2f}</code>\n\n"
                f"🛑 <b>Stop Loss:</b> <code>{signal_db.sl:.2f}</code>\n"
                f"🎯 <b>Take Profit:</b> <code>{signal_db.tp:.2f}</code>\n\n"
                f"📊 <b>Risk Management:</b>\n"
                f"• Lot: <b>{lot_size}</b> (Balans $1000)\n"
                f"• R/R Ratio: <b>1:{rr_ratio:.1f}</b>\n\n"
                f"📝 <b>Sabab:</b> {signal_db.reason}\n"
                f"⏰ <b>Vaqt:</b> <code>{time_str}</code>"
            )

            CHANNEL_ID = os.getenv("CHANNEL_ID")
            try:
                await context.bot.send_message(chat_id=CHANNEL_ID, text=channel_msg, parse_mode='HTML')
                db.update_signal_status(signal_id, "published")
                await query.edit_message_text(f"{query.message.text_html}\n\n✅ <b>Kanalga chiqarildi!</b>", parse_mode='HTML')
            except Exception as e:
                logger.error(f"Error: {e}")

    elif query.data.startswith('sigrej_'):
        signal_id = int(query.data.split('_')[1])
        db.update_signal_status(signal_id, "rejected")
        await query.edit_message_text(f"{query.message.text_html}\n\n❌ <b>Rad etildi.</b>", parse_mode='HTML')

    elif query.data == 'back_main':
        t = TEXTS[lang]
        keyboard = [
            [InlineKeyboardButton(t['tariffs_btn'], callback_data='tariffs')],
            [InlineKeyboardButton(t['profile_btn'], callback_data='profile')],
            [InlineKeyboardButton(t['status_btn'], callback_data='status')],
            [InlineKeyboardButton(t['settings_btn'], callback_data='settings')],
        ]
        # Bu yerda Inline bo'lgani uchun inline tugmalar orqali navigatsiya qilish kerak edi
        # Lekin glavniy menyu ReplyKeyboardda. Shuning uchun shunchaki matnni o'zgartiramiz.
        # Aslida 'back_main' bu inline menu ichidagi orqaga.
        
        await query.edit_message_text(t['back_to_main'], reply_markup=None) # Yoki shunchaki xabarni o'chirib Reply menu ishlatish

async def grant_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID: return
    args = context.args
    if len(args) < 2: return
    user_id, days = args[0], int(args[1])
    end_date = db.grant_subscription(user_id, days)
    await update.message.reply_text(f"✅ User {user_id} ga {days} kunlik obuna berildi.")

async def signal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID: return

    try:
        args = context.args
        if len(args) < 4:
            await update.message.reply_text("⚠️ Format: /signal TYPE PRICE SL TP [REASON]\nEx: /signal BUY 2030 2025 2045 Pullback")
            return

        sig_type = args[0].upper()
        if sig_type not in ['BUY', 'SELL']:
            await update.message.reply_text("⚠️ Type must be BUY or SELL")
            return
            
        price = float(args[1])
        sl = float(args[2])
        tp = float(args[3])
        reason = " ".join(args[4:]) if len(args) > 4 else "Manual Signal"

        signal_id = db.log_signal("XAU/USD", sig_type, price, sl, tp, reason)

        sl_dist = abs(price - sl)
        tp_dist = abs(tp - price)
        rr = tp_dist / sl_dist if sl_dist != 0 else 0
        lot = 10 / (sl_dist * 100) if sl_dist != 0 else 0.01
        lot = max(0.01, round(lot, 2))

        admin_msg = (
            f"📝 <b>MANUAL SIGNAL PREVIEW</b>\n\n"
            f"Type: <b>{sig_type}</b>\n"
            f"Price: {price:.2f}\n"
            f"SL: {sl:.2f} | TP: {tp:.2f}\n"
            f"R/R: 1:{rr:.1f} | Lot: {lot}\n"
            f"Reason: {reason}\n\n"
            f"Publish to channel?"
        )
        
        kb = [[InlineKeyboardButton("✅ Ha", callback_data=f"sigpub_{signal_id}"),
               InlineKeyboardButton("❌ Yo'q", callback_data=f"sigrej_{signal_id}")]]
               
        await update.message.reply_text(admin_msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')

    except Exception as e:
        logger.error(f"Manual signal error: {e}")

# --- CONVERSATION HANDLERS FOR MANUAL SIGNAL ---

async def start_signal_creation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        return ConversationHandler.END
    
    chat_id = update.effective_chat.id
    t = TEXTS[db.get_user_language(chat_id)]
        
    keyboard = [[KeyboardButton("BUY"), KeyboardButton("SELL")], [KeyboardButton(t['cancel'])]]
    await update.message.reply_text(
        t['manual_signal_start'],
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True),
        parse_mode='HTML'
    )
    return SIGNAL_TYPE

async def get_signal_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    t = TEXTS[db.get_user_language(chat_id)]
    text = update.message.text
    
    if text == t['cancel']:
        await update.message.reply_text(t['cancelled'], reply_markup=get_main_keyboard(chat_id))
        return ConversationHandler.END
        
    if text not in ["BUY", "SELL"]:
        await update.message.reply_text(t['error_type'])
        return SIGNAL_TYPE
        
    context.user_data['sig_type'] = text
    await update.message.reply_text(
        get_text(chat_id, 'manual_signal_price', type=text), 
        parse_mode='HTML', 
        reply_markup=ReplyKeyboardMarkup([[KeyboardButton(t['cancel'])]], resize_keyboard=True)
    )
    return SIGNAL_PRICE

async def get_signal_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    t = TEXTS[db.get_user_language(chat_id)]
    text = update.message.text
    
    if text == t['cancel']:
        await update.message.reply_text(t['cancelled'], reply_markup=get_main_keyboard(chat_id))
        return ConversationHandler.END
    
    try:
        price = float(text)
        context.user_data['price'] = price
        await update.message.reply_text(get_text(chat_id, 'manual_signal_sl', price=price), parse_mode='HTML')
        return SIGNAL_SL
    except ValueError:
        await update.message.reply_text(t['error_num'])
        return SIGNAL_PRICE

async def get_signal_sl(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    t = TEXTS[db.get_user_language(chat_id)]
    text = update.message.text
    
    if text == t['cancel']:
        return ConversationHandler.END
        
    try:
        sl = float(text)
        context.user_data['sl'] = sl
        await update.message.reply_text(get_text(chat_id, 'manual_signal_tp', sl=sl), parse_mode='HTML')
        return SIGNAL_TP
    except ValueError:
        await update.message.reply_text(t['error_num'])
        return SIGNAL_SL

async def get_signal_tp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    t = TEXTS[db.get_user_language(chat_id)]
    text = update.message.text
    
    if text == t['cancel']:
        return ConversationHandler.END
        
    try:
        tp = float(text)
        context.user_data['tp'] = tp
        await update.message.reply_text(get_text(chat_id, 'manual_signal_reason', tp=tp), parse_mode='HTML')
        return SIGNAL_REASON
    except ValueError:
        await update.message.reply_text(t['error_num'])
        return SIGNAL_TP

async def get_signal_reason(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    t = TEXTS[db.get_user_language(chat_id)]
    text = update.message.text
    
    if text == t['cancel']:
        return ConversationHandler.END
        
    context.user_data['reason'] = text
    
    sig_type = context.user_data['sig_type']
    price = context.user_data['price']
    sl = context.user_data['sl']
    tp = context.user_data['tp']
    reason = context.user_data['reason']
    
    signal_id = db.log_signal("XAU/USD", sig_type, price, sl, tp, reason)
    
    sl_dist = abs(price - sl)
    tp_dist = abs(tp - price)
    rr = tp_dist / sl_dist if sl_dist != 0 else 0
    lot = 10 / (sl_dist * 100) if sl_dist != 0 else 0.01
    lot = max(0.01, round(lot, 2))

    preview_msg = (
        f"📝 <b>MANUAL SIGNAL PREVIEW</b>\n\n"
        f"Type: <b>{sig_type}</b>\n"
        f"Price: {price:.2f}\n"
        f"SL: {sl:.2f} | TP: {tp:.2f}\n"
        f"R/R: 1:{rr:.1f} | Lot: {lot}\n"
        f"Reason: {reason}\n\n"
        f"Publish to channel?"
    )
    
    kb = [[InlineKeyboardButton("✅ Ha", callback_data=f"sigpub_{signal_id}"),
           InlineKeyboardButton("❌ Yo'q", callback_data=f"sigrej_{signal_id}")]]
    
    await update.message.reply_text(t['manual_signal_preview'], reply_markup=get_main_keyboard(chat_id))
    await update.message.reply_text(preview_msg, reply_markup=InlineKeyboardMarkup(kb), parse_mode='HTML')
    
    return ConversationHandler.END

async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    t = TEXTS[db.get_user_language(chat_id)]
    await update.message.reply_text(t['cancelled'], reply_markup=get_main_keyboard(chat_id))
    return ConversationHandler.END

async def join_request_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    request = update.chat_join_request
    if not request: return
    user_id = request.from_user.id
    sub = db.get_subscription(user_id)
    if sub and sub.is_active:
        try:
            await request.approve()
            await context.bot.send_message(chat_id=user_id, text="✅ <b>Xush kelibsiz!</b> Obunangiz faol.") # Localization needed here too eventually
        except Exception as e: logger.error(f"Error: {e}")
