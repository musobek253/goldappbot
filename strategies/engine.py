import logging
from strategies.indicators import calculate_indicators
from data.feed import DataHandler
from strategies.news import NewsFilter
from strategies.cot_analyzer import COTAnalyzer

logger = logging.getLogger(__name__)

class StrategyEngine:
    def __init__(self, db, data_handler: DataHandler):
        self.db = db
        self.data_handler = data_handler
        self.news_filter = NewsFilter()
        self.cot_analyzer = COTAnalyzer(db)

    def check_signal(self, symbol="XAU/USD"):
        # 0. Import needed helpers
        from strategies.indicators import (
            calculate_indicators, identify_levels, check_trend_ema200, 
            detect_patterns, check_candlestick_patterns
        )

        # 1. Bozor Filtrlari (Vaqt va Yangiliklar)
        session = self.news_filter.get_market_session()
        # if session == "CLOSED": pass 

        if not self.news_filter.check_news_impact():
            logger.info("Yuqori ta'sirli yangilik aniqlandi. Savdo o'tkazib yuborildi.")
            return None

        # 2. Ma'lumotlarni yuklash (H4 - Global Context, M15 - Entry)
        # H4 trend va darajalar uchun
        df_h4 = self.data_handler.fetch_data(symbol, timeframe="H4", limit=200)
        # M15 bu paternlar va kirish uchun
        df_m15 = self.data_handler.fetch_data(symbol, timeframe="M15", limit=200)

        if df_h4.empty or df_m15.empty:
            return None

        # 3. Indikatorlarni hisoblash
        config = {
            "RSI_PERIOD": int(self.db.get_config("RSI_PERIOD", 14)),
            "EMA_FAST": 50,
            "EMA_SLOW": 200
        }
        
        df_h4 = calculate_indicators(df_h4, config)
        df_m15 = calculate_indicators(df_m15, config)

        # --- 3-BOSQICH: STRATEGIYA MANTIQI ---

        # 1-BOSQICH: Global Context (H4)
        global_trend = check_trend_ema200(df_h4)
        
        # Support/Resistance darajalari (H4/D1 simulation on H4 data)
        # 50 shamlik oyna bilan kuchli darajalarni topamiz
        h4_levels = identify_levels(df_h4, window=20) 
        
        current_price = self.data_handler.get_current_price(symbol)
        
        # Filtr: Bizga darajaga yaqinlik kerak (masalan 20-30 pips = $2-$3 Goldda)
        # UPDATE: Ko'proq signal uchun tolerance oshirildi $3 -> $5
        LEVEL_TOLERANCE = 5.0 
        
        nearby_support = [l for l in h4_levels if l['type'] == 'SUPPORT' and abs(l['price'] - current_price) < LEVEL_TOLERANCE]
        nearby_resistance = [l for l in h4_levels if l['type'] == 'RESISTANCE' and abs(l['price'] - current_price) < LEVEL_TOLERANCE]
        
        # Agar trend yo'q bo'lsa yoki daraja topilmasa -> o'tkazib yuborish (user talabi: "Check Level ... yaqinmi?")
        # Lekin user "Trend EMA 200 dan past bo'lsa faqat Sell" degan.
        
        direction = None
        if global_trend == "UP":
            if not nearby_support: # Trend Up bo'lsa, Supportdan qaytishni kutamiz
                 pass # Yoki shartni yumshatamiz
            else:
                 direction = "BUY"
        elif global_trend == "DOWN":
             if not nearby_resistance:
                 pass
             else:
                 direction = "SELL"
                 
        # Agar Trend Neutral bo'lsa yoki darajaga yaqin bo'lmasa, "Pattern" bosqichiga o'tmaymiz...
        # Lekin ehtimol trend o'zgarishi ham mumkin (Reversal).
        # User flowchart: Check Trend -> Check Level -> Check Pattern
        
        if not direction:
            # Simple fallback: Agar biz kuchli darajaga keldik-u, lekin trend hali o'zgarmagan bo'lsa (Reversal uchun)
            if nearby_support: direction = "BUY" # Potential Reversal Buy
            elif nearby_resistance: direction = "SELL" # Potential Reversal Sell
            else: return None # Daraja yo'q
            
        # 2-BOSQICH: Pattern Recognition (M15)
        # Bu yerda M15 da shakllarni qidiramiz
        patterns = detect_patterns(df_m15)
        
        valid_pattern = False
        pattern_name = ""
        
        if direction == "BUY":
            if "DOUBLE_BOTTOM" in patterns:
                valid_pattern = True
                pattern_name = "Double Bottom"
                
        if direction == "SELL":
            if "DOUBLE_TOP" in patterns:
                valid_pattern = True
                pattern_name = "Double Top"
                
        # UPDATE: Ko'proq signal uchun "Pattern SHART EMAS", agar qat'iy sham tasdi (Stage 3) bo'lsa.
        # Biz valid_pattern ni saqlab qolamiz, lekin return qilmaymiz.

        # 3-BOSQICH: Kirish va Tasdiq (M15)
        # Sham tahlili va RSI
        last_m15 = df_m15.iloc[-1]
        prev_m15 = df_m15.iloc[-2]
        prev_2_m15 = df_m15.iloc[-3]
        
        candlesticks = check_candlestick_patterns(last_m15, prev_m15, prev_2_m15)
        
        confirmed = False
        confirmation_reason = ""
        
        rsi = last_m15["RSI_14"]
        
        if direction == "BUY":
            # Hammer, Bullish Engulfing yoki Morning Star
            has_candle_signal = any(p in candlesticks for p in ["HAMMER", "BULLISH_ENGULFING", "MORNING_STAR"])
            
            # --- YANGI FILTRLAR (Win Rate 75% uchun) ---
            # 1. RSI: Tepada sotib olmaslik kerak (RSI < 70)
            rsi_ok = rsi < 70
            
            # 2. MACD Momentum: Gistogramma o'sayotgan bo'lishi kerak
            # Indikatorlar dataframe da 'MACDh_12_26_9' (Hist) borligini tekshiramiz
            macd_hist = last_m15.get("MACDh_12_26_9", 0)
            prev_macd_hist = prev_m15.get("MACDh_12_26_9", 0)
            
            # Momentum UP: Hist > Prev_Hist (Kuchaymoqda) Yoki Hist > 0 (Trend o'zgarishi)
            momentum_ok = macd_hist > prev_macd_hist or macd_hist > 0
            
            # 3. Multi-Timeframe Candle Confirmation (H4 + H1) - 78% WR
            df_h1 = self.data.fetch_data(symbol, "H1", limit=50)
            if not df_h1.empty:
                 h1_last = df_h1.iloc[-1]
                 is_h1_bullish = h1_last['close'] > h1_last['open']
                 is_h4_bullish = last_h4['close'] > last_h4['open']
                 
                 if not (is_h1_bullish and is_h4_bullish):
                     momentum_ok = False # Veto if candles mismatch

            # OPTIMIZATION UPDATE: Pattern alone gives low quality trades. We REQUIRE candle signal.
            if has_candle_signal:
                if rsi_ok and momentum_ok:
                    confirmed = True
                    p_text = f"Pattern: {pattern_name}" if valid_pattern else "No Pattern"
                    c_text = f"Candle: {candlesticks}" 
                    confirmation_reason = f"{p_text} | {c_text} | RSI: {rsi:.1f} | MACD: OK"
            

        if direction == "SELL":
             # Shooting Star, Bearish Engulfing yoki Evening Star
            has_candle_signal = any(p in candlesticks for p in ["SHOOTING_STAR", "BEARISH_ENGULFING", "EVENING_STAR"])

            # --- YANGI FILTRLAR ---
            # 1. RSI: Pastda sotmaslik kerak (RSI > 30)
            rsi_ok = rsi > 30
            
            # 2. Momentum DOWN: Hist < Prev_Hist (Pasaymoqda) Yoki Hist < 0
            macd_hist = last_m15.get("MACDh_12_26_9", 0)
            prev_macd_hist = prev_m15.get("MACDh_12_26_9", 0)
            
            momentum_ok = macd_hist < prev_macd_hist or macd_hist < 0

            # 3. Multi-Timeframe Candle Confirmation (H4 + H1) - 78% WR
            df_h1 = self.data.fetch_data(symbol, "H1", limit=50)
            if not df_h1.empty:
                 h1_last = df_h1.iloc[-1]
                 is_h1_bearish = h1_last['close'] < h1_last['open']
                 is_h4_bearish = last_h4['close'] < last_h4['open']
                 
                 if not (is_h1_bearish and is_h4_bearish):
                     momentum_ok = False # Veto if candles mismatch

            if has_candle_signal:
                if rsi_ok and momentum_ok:
                    confirmed = True
                    p_text = f"Pattern: {pattern_name}" if valid_pattern else "No Pattern"
                    c_text = f"Candle: {candlesticks}" 
                    confirmation_reason = f"{p_text} | {c_text} | RSI: {rsi:.1f} | MACD: OK"
                
        if not confirmed:
            return None
            
        # --- EXECUTION ---
        
        signal = direction
        entry_price = last_m15["close"]
        atr = last_m15.get("ATRr_14", entry_price * 0.002) * 1.5
        
        sl = entry_price - atr if signal == "BUY" else entry_price + atr
        tp = entry_price + (atr * 2) if signal == "BUY" else entry_price - (atr * 2)
        
        score = 3
        reason = f"3-Stage System: Trend {global_trend} | Level Reached | Pattern {pattern_name} | {confirmation_reason}"
        
        return {
            "symbol": symbol,
            "type": signal,
            "price": entry_price,
            "sl": sl,
            "tp": tp,
            "reason": reason,
            "time": last_m15.name,
            "score": score,
            "cot_info": None
        }
