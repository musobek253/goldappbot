import logging
from .indicators import calculate_indicators
from ..data.feed import DataHandler
from .news import NewsFilter
from .cot_analyzer import COTAnalyzer

logger = logging.getLogger(__name__)

class StrategyEngine:
    def __init__(self, db, data_handler: DataHandler):
        self.db = db
        self.data_handler = data_handler
        self.news_filter = NewsFilter()
        self.cot_analyzer = COTAnalyzer(db)

    def check_signal(self, symbol="XAU/USD"):
        # 1. Bozor Filtrlari (Vaqt va Yangiliklar)
        session = self.news_filter.get_market_session()
        if session == "CLOSED":
            # return None 
            pass

        if not self.news_filter.check_news_impact():
            logger.info("Yuqori ta'sirli yangilik aniqlandi. Savdo o'tkazib yuborildi.")
            return None

        # 2. COT Tahlili (Fundamental)
        cot_data = None
        if symbol == "XAU/USD":
            cot_data = self.cot_analyzer.analyze()

        # 3. Ikki xil Timeframe ma'lumotlarini yuklash (Technical)
        df_m15 = self.data_handler.fetch_data(symbol, timeframe="M15", limit=100)
        df_m5 = self.data_handler.fetch_data(symbol, timeframe="M5", limit=100)

        if df_m15.empty or df_m5.empty:
            return None

        # 4. Indikatorlarni hisoblash
        config = {
            "RSI_PERIOD": int(self.db.get_config("RSI_PERIOD", 14)),
            "EMA_FAST": 50,
            "EMA_SLOW": 200
        }
        
        df_m15 = calculate_indicators(df_m15, config)
        df_m5 = calculate_indicators(df_m5, config)

        # 5. Mantiqiy baholash & Sentiment Scoring
        signal = None
        reason = []
        sentiment_score = 0 # 0 dan 3 gacha ball

        # --- COT (Fundamental) ---
        if cot_data:
            cot_sentiment = cot_data.get('sentiment')
            if cot_sentiment in ["BULLISH", "REVERSAL_BULLISH"]:
                sentiment_score += 1
                reason.append("COT: BULLISH (+1)")
            elif cot_sentiment in ["BEARISH", "REVERSAL_BEARISH"]:
                sentiment_score -= 1 # Buy uchun minus, Sell uchun keyinroq abs() qilamiz
                reason.append("COT: BEARISH (-1)")

        # --- Trend (M15 - Technical) ---
        last_m15 = df_m15.iloc[-1]
        trend = "NEUTRAL"
        if last_m15["close"] > last_m15["EMA_200"]:
            trend = "UP"
            sentiment_score += 1
            reason.append("EMA: TREND UP (+1)")
        elif last_m15["close"] < last_m15["EMA_200"]:
            trend = "DOWN"
            sentiment_score -= 1
            reason.append("EMA: TREND DOWN (-1)")
        
        # --- RSI (Technical) ---
        last_m5 = df_m5.iloc[-1]
        rsi_m5 = last_m5["RSI_14"]
        if rsi_m5 < 40: # Oversold yaqin
            sentiment_score += 1
            reason.append(f"RSI: M5 LOW({rsi_m5:.1f}) (+1)")
        elif rsi_m5 > 60: # Overbought yaqin
            sentiment_score -= 1
            reason.append(f"RSI: M5 HIGH({rsi_m5:.1f}) (-1)")

        # YAKUNIY QAROR
        # sentiment_score: +3 bo'lsa BUY uchun kuchli, -3 bo'lsa SELL uchun kuchli
        if sentiment_score >= 2:
            signal = "BUY"
        elif sentiment_score <= -2:
            signal = "SELL"

        if signal:
            price = self.data_handler.get_current_price(symbol)
            atr = last_m15.get("ATRr_14", price * 0.003) * 1.5 
            
            sl = price - atr if signal == "BUY" else price + atr
            tp = price + (atr * 2) if signal == "BUY" else price - (atr * 2)

            # Signal darajasi
            strength = "KUCHLI" if abs(sentiment_score) == 3 else "O'RTA"
            
            return {
                "symbol": symbol,
                "type": signal,
                "price": price,
                "sl": sl,
                "tp": tp,
                "reason": f"[{strength}] | " + " | ".join(reason),
                "time": last_m5.name,
                "score": abs(sentiment_score),
                "cot_info": cot_data if symbol == "XAU/USD" else None
            }

        return None
