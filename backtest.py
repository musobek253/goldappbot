import pandas as pd
import numpy as np
from data.feed import DataHandler
from strategies.indicators import (
    calculate_indicators, identify_levels, check_trend_ema200, 
    detect_patterns, check_candlestick_patterns
)
import logging

# Loglarni o'chirish (toza output uchun)
logging.getLogger("treding.data.feed").setLevel(logging.ERROR)

def run_backtest(symbol="XAU/USD"):
    print(f"--- {symbol} uchun 3-Bosqichli Strategiya Backtesti (1 Oy) ---")
    print("Ma'lumotlar yuklanmoqda...")
    
    data = DataHandler()
    
    # 1. Ma'lumotlarni yuklash (60 kunlik - indikatorlar hisoblash uchun zaxira bilan)
    # H4 - Global Context
    df_h4 = data.fetch_data(symbol, "H4", limit=1000)
    # M15 - Entry (60 kun ~ 5000-6000 sham)
    df_m15 = data.fetch_data(symbol, "M15", limit=6000)
    # H1 - Context
    df_h1 = data.fetch_data(symbol, "H1", limit=2000)
    
    if df_h4.empty or df_m15.empty:
        print("Ma'lumotlar yetarli emas!")
        return

    # 2. Indikatorlar
    config = {"RSI_PERIOD": 14, "EMA_FAST": 50, "EMA_SLOW": 200}
    df_h4 = calculate_indicators(df_h4, config)
    df_m15 = calculate_indicators(df_m15, config)
    
    # Simulyatsiya
    balance = 1000
    trades = []
    
    # H4 ma'lumotlarini tezkor qidirish uchun dictionaryga o'tkazish (optimization)
    # Aslida M15 sham vaqtiga mos keladigan H4 shamni topishimiz kerak.
    # Oddiy yo'l: Har bir M15 stepda filter qilish (sekin)
    # Tezkor yo'l: `asof` merge yoki shunchaki oxirgi indexni saqlash.
    
    print(f"Simulyatsiya boshlandi... (Jami {len(df_m15)} M15 sham)")
    
    # Backtest start index (kamida 200 sham o'tkazib yuboramiz - indikatorlar uchun)
    start_index = 200
    
    for i in range(start_index, len(df_m15)):
        # Progress bar
        if i % 500 == 0:
            print(f"Kuzatuv: {i}/{len(df_m15)} sham...")
            
        current_m15_row = df_m15.iloc[i]
        current_time = current_m15_row.name
        
        # 1. H4 Contextni olish (Look-ahead bias bo'lmasligi uchun current_time dan kichik yoki teng)
        # Biz H4 ning yopilgan shamlarini olishimiz kerak.
        # current_time - bu M15 ning close time'i.
        
        # H4 dagi mos keluvchi oxirgi yopilgan shamni topish
        h4_subset = df_h4[df_h4.index <= current_time]
        if h4_subset.empty: continue
        
        # Strategy Logic Replica
        
        # --- STAGE 1: Global Trend & Levels (H4) ---
        global_trend = check_trend_ema200(h4_subset)
        
        # Levels - H4 slice ni ishlatamiz
        h4_slice_for_levels = h4_subset.tail(100) # Oxirgi 100 ta H4 sham
        h4_levels = identify_levels(h4_slice_for_levels, window=10)
        
        current_price = current_m15_row['close']
        # UPDATE: Tolerance $5.0
        LEVEL_TOLERANCE = 5.0
        
        nearby_support = [l for l in h4_levels if l['type'] == 'SUPPORT' and abs(l['price'] - current_price) < LEVEL_TOLERANCE]
        nearby_resistance = [l for l in h4_levels if l['type'] == 'RESISTANCE' and abs(l['price'] - current_price) < LEVEL_TOLERANCE]
        
        direction = None
        if global_trend == "UP" and nearby_support:
            direction = "BUY"
        elif global_trend == "DOWN" and nearby_resistance:
            direction = "SELL"
            
        # Fallback (Reversal) logic from engine.py
        if not direction:
            if nearby_support: direction = "BUY"
            elif nearby_resistance: direction = "SELL"
            else: continue
            
        # --- STAGE 2: Patterns (M15) ---
        # M15 slice
        m15_slice = df_m15.iloc[i-50:i+1] # Songi 50 ta sham
        patterns = detect_patterns(m15_slice)
        
        valid_pattern = False
        if direction == "BUY" and "DOUBLE_BOTTOM" in patterns: valid_pattern = True
        if direction == "SELL" and "DOUBLE_TOP" in patterns: valid_pattern = True
        
        # UPDATE: Pattern optional. We continue to check candlesticks.
        
        # --- STAGE 3: Entry (M15) ---
        last_m15 = df_m15.iloc[i]
        prev_m15 = df_m15.iloc[i-1]
        prev_2_m15 = df_m15.iloc[i-2]
        
        candlesticks = check_candlestick_patterns(last_m15, prev_m15, prev_2_m15)
        
        entry_signal = False
        # H1 Context
        h1_subset = df_h1[df_h1.index <= current_time]
        
        if direction == "BUY":
            has_candle = any(p in candlesticks for p in ["HAMMER", "BULLISH_ENGULFING", "MORNING_STAR"])
            
            rsi_ok = last_m15.get("RSI_14") < 70
            
            macd_hist = last_m15.get("MACDh_12_26_9", 0)
            prev_macd_hist = prev_m15.get("MACDh_12_26_9", 0)
            momentum_ok = macd_hist > prev_macd_hist or macd_hist > 0
            
            # H1 & H4 Confirmation
            if not h1_subset.empty and not h4_subset.empty:
                 h1_last = h1_subset.iloc[-1]
                 h4_last = h4_subset.iloc[-1]
                 is_h1_bullish = h1_last['close'] > h1_last['open']
                 is_h4_bullish = h4_last['close'] > h4_last['open']
                 
                 if not (is_h1_bullish and is_h4_bullish):
                     momentum_ok = False # Veto
    
            if has_candle:
                if rsi_ok and momentum_ok:
                    entry_signal = True
                
        elif direction == "SELL":
             has_candle = any(p in candlesticks for p in ["SHOOTING_STAR", "BEARISH_ENGULFING", "EVENING_STAR"])
             
             rsi_ok = last_m15.get("RSI_14") > 30 
             
             macd_hist = last_m15.get("MACDh_12_26_9", 0)
             prev_macd_hist = prev_m15.get("MACDh_12_26_9", 0)
             momentum_ok = macd_hist < prev_macd_hist or macd_hist < 0
             
             if not h1_subset.empty and not h4_subset.empty:
                 h1_last = h1_subset.iloc[-1]
                 h4_last = h4_subset.iloc[-1]
                 is_h1_bearish = h1_last['close'] < h1_last['open']
                 is_h4_bearish = h4_last['close'] < h4_last['open']
                 
                 if not (is_h1_bearish and is_h4_bearish):
                     momentum_ok = False
    
             if has_candle:
                 if rsi_ok and momentum_ok:
                    entry_signal = True
                
        if entry_signal:
             # Trade Execution Simulation
             entry_price = current_price
             atr = last_m15.get("ATRr_14", entry_price * 0.002) * 1.5
             
             sl = entry_price - atr if direction == "BUY" else entry_price + atr
             tp = entry_price + (atr * 2) if direction == "BUY" else entry_price - (atr * 2)
             
             # Oddiy natijani tekshirish (pips)
             # Keyingi 4 soat (16 ta M15 sham) ichida nima bo'ldi?
             future_candles = df_m15.iloc[i+1:i+20]
             
             outcome = "BE" # Breakeven default
             pnl = 0
             
             for _, future_row in future_candles.iterrows():
                 high = future_row['high']
                 low = future_row['low']
                 
                 if direction == "BUY":
                     if low <= sl:
                         outcome = "LOSS"
                         pnl = sl - entry_price
                         break
                     if high >= tp:
                         outcome = "WIN"
                         pnl = tp - entry_price
                         break
                 elif direction == "SELL":
                     if high >= sl:
                         outcome = "LOSS"
                         pnl = entry_price - sl
                         break
                     if low <= tp:
                         outcome = "WIN"
                         pnl = entry_price - tp
                         break
             
             # Agar vaqt tugasa va SL/TP bo'lmasa, current price da yopamiz
             if outcome == "BE" and not future_candles.empty:
                 exit_price = future_candles.iloc[-1]['close']
                 if direction == "BUY": pnl = exit_price - entry_price
                 else: pnl = entry_price - exit_price
                 outcome = "CLOSE"
                 
             trades.append({
                 "time": current_time,
                 "type": direction,
                 "price": entry_price,
                 "outcome": outcome,
                 "pnl": pnl
             })
             
             # Savdo ochilgandan keyin biroz kutish (cooldown) - masalan keyingi 10 sham
             # i += 10 # Loop ichida i ni o'zgartirib bo'lmaydi, lekin biz shunchaki continue qilishimiz mumkin
             # Real loopda bu murakkabroq, shuning uchun shunchaki davom etamiz.
             
    # Natijalar
    total_trades = len(trades)
    wins = len([t for t in trades if t['pnl'] > 0])
    losses = len([t for t in trades if t['pnl'] < 0])
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
    total_pnl = sum([t['pnl'] for t in trades])
    
    if trades:
        print("\n--- BARCHA SAVDOLAR RO'YXATI ---")
        print(f"{'VAQT (UTC)':<25} | {'TUR':<5} | {'NATIJA':<6} | {'PnL':<8}")
        print("-" * 55)
        for t in trades:
            print(f"{str(t['type']):<5} | {t['outcome']:<6} | {t['pnl']:.2f} | {t['time']}")

    print("\n--- BACKTEST NATIJALARI (YAKUNIY) ---")
    print(f"Jami Savdolar: {total_trades}")
    print(f"Yutuqlar: {wins}")
    print(f"Yo'qotishlar: {losses}")
    print(f"Win Rate: {win_rate:.2f}%")
    print(f"Total PnL (Price diff): {total_pnl:.2f}")

if __name__ == "__main__":
    run_backtest()
