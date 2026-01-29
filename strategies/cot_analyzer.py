import requests
import pandas as pd
import logging
from datetime import datetime, timedelta
import os

logger = logging.getLogger(__name__)

class COTAnalyzer:
    """
    CFTC COT (Commitment of Traders) hisobotlarini tahlil qilish moduli.
    Yirik o'yinchilar (Hedge fondlar) kayfiyatini aniqlaydi.
    """
    def __init__(self, db):
        self.db = db
        # Socrata API - Disaggregated Futures Only (Oltin uchun eng mos)
        # Managed Money -> "Smart Money" (Hedge fondlar) uchun proksi
        self.dataset_id = "72hh-3qpy"
        self.api_url = f"https://publicreporting.cftc.gov/resource/{self.dataset_id}.json"
        self.lookback_period = 52 # Standart: 52 hafta
        self.threshold = 0.10   # 10% o'zgarish bo'sag'asi
        
        # Keshlangan natijalar
        self.last_analysis = None
        self.last_fetch_time = None

    def fetch_cot_data(self, limit=100):
        """
        CFTC API dan Oltin bo'yicha oxirgi hisobotlarni yuklab oladi.
        """
        params = {
            "$where": "market_and_exchange_names like '%GOLD - NEW YORK MERCANTILE EXCHANGE%'",
            "$limit": limit,
            "$order": "report_date_as_yyyy_mm_dd DESC"
        }
        
        try:
            logger.info("CFTC dan COT ma'lumotlari yuklanmoqda...")
            response = requests.get(self.api_url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if not data:
                logger.warning("CFTC dan Oltin bo'yicha ma'lumot topilmadi.")
                return None
                
            df = pd.DataFrame(data)
            
            # Kerakli ustunlarni raqamlarga o'tkazish
            cols_to_numeric = [
                'm_money_positions_long_all', 
                'm_money_positions_short_all', 
                'open_interest_all'
            ]
            for col in cols_to_numeric:
                df[col] = pd.to_numeric(df[col], errors='coerce')
                
            df['report_date'] = pd.to_datetime(df['report_date_as_yyyy_mm_dd'])
            df = df.sort_values('report_date', ascending=True)
            
            return df
            
        except Exception as e:
            logger.error(f"COT ma'lumotlarini yuklashda xatolik: {e}")
            return None

    def analyze(self):
        """
        COT ma'lumotlarini tahlil qiladi va Sentiment Score qaytaradi.
        """
        # Faqat kuniga bir marta yoki kesh bo'sh bo'lsa yangilash
        now = datetime.now()
        if self.last_analysis and self.last_fetch_time:
            if (now - self.last_fetch_time) < timedelta(hours=12):
                return self.last_analysis

        df = self.fetch_cot_data()
        if df is None or len(df) < 2:
            return {"sentiment": "NEUTRAL", "score": 0, "details": "Ma'lumot kam"}

        # Oxirgi va undan oldingi xabarlar
        current = df.iloc[-1]
        previous = df.iloc[-2]
        
        # 1. Net Position (Long - Short)
        net_curr = current['m_money_positions_long_all'] - current['m_money_positions_short_all']
        net_prev = previous['m_money_positions_long_all'] - previous['m_money_positions_short_all']
        
        # Net Position o'zgarishi
        net_change_pct = 0
        if abs(net_prev) > 0:
            net_change_pct = (net_curr - net_prev) / abs(net_prev)

        # 2. COT Index (Willco) - 52 hafta
        lookback_df = df.tail(self.lookback_period)
        net_positions = lookback_df['m_money_positions_long_all'] - lookback_df['m_money_positions_short_all']
        
        min_net = net_positions.min()
        max_net = net_positions.max()
        
        cot_index = 0
        if max_net != min_net:
            cot_index = (net_curr - min_net) / (max_net - min_net) * 100

        # 3. Signal Shartlari
        sentiment = "NEUTRAL"
        score = 0
        details = []

        # Trend tahlili
        if net_change_pct > self.threshold:
            sentiment = "BULLISH"
            score = 1
            details.append(f"Hedge-fondlar rekord darajada sotib olishmoqda (+{net_change_pct*100:.1f}%)")
        elif net_change_pct < -self.threshold:
            sentiment = "BEARISH"
            score = -1
            details.append(f"Hedge-fondlar sotishni boshladi ({net_change_pct*100:.1f}%)")

        # Reversal (Qayrilish) punktlari
        if cot_index > 90:
            details.append("Bozor haddan tashqari sotib olingan (Overbought)")
            if sentiment == "BULLISH": sentiment = "REVERSAL_BEARISH"
        elif cot_index < 10:
            details.append("Bozor haddan tashqari sotilgan (Oversold)")
            if sentiment == "BEARISH": sentiment = "REVERSAL_BULLISH"

        result = {
            "sentiment": sentiment,
            "score": score,
            "cot_index": round(cot_index, 1),
            "net_change": round(net_change_pct * 100, 1),
            "long": int(current['m_money_positions_long_all']),
            "short": int(current['m_money_positions_short_all']),
            "details": " | ".join(details)
        }
        
        self.last_analysis = result
        self.last_fetch_time = now
        return result

    def get_summary_message(self, analysis):
        """
        Telegram uchun COT xabari matnini tayyorlaydi.
        """
        emoji = "📈" if analysis['sentiment'] in ["BULLISH", "REVERSAL_BULLISH"] else "📉"
        trend_text = "Bullish (Buqalarcha)" if analysis['score'] > 0 else "Bearish (Ayiqcha)"
        if analysis['score'] == 0: trend_text = "Neytral"

        msg = (
            f"🏦 <b>SMART MONEY ALERT: GOLD</b>\n\n"
            f"Trend: Hedge-fondlar pozitsiyasi <b>{analysis['net_change']:+g}%</b> o'zgardi.\n"
            f"Sentiment: <b>{trend_text} {emoji}</b>\n"
            f"COT Index: <b>{analysis['cot_index']}%</b>\n\n"
            f"📝 <b>Tahlil:</b> {analysis['details']}\n"
            f"💡 <b>Tavsiya:</b> Texnik tahlil (RSI/EMA) orqali kirish nuqtasini qidiring."
        )
        return msg
