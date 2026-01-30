import pandas as pd
import numpy as np
from data.feed import DataHandler
from strategies.indicators import (
    calculate_indicators, identify_levels, check_trend_ema200, 
    detect_patterns, check_candlestick_patterns
)
import logging

logging.getLogger("treding.data.feed").setLevel(logging.ERROR)

def run_scenario(df_h4, df_m15, scenario_name, candle_types, rsi_min, rsi_max, use_macd):
    print(f"\n--- Scenario: {scenario_name} ---")
    
    # Indikatorlar dataframe da bo'lishi kerak. Ular tashqarida hisoblangan.
    
    trades = []
    
    start_index = 200
    
    # H4 optimization
    h4_levels_cache = {} # Simple cache mechanism if needed, but linear scan is fine for this scale
    
    for i in range(start_index, len(df_m15)):
        current_m15_row = df_m15.iloc[i]
        current_time = current_m15_row.name
        
        # 1. Global Context
        h4_subset = df_h4[df_h4.index <= current_time]
        if h4_subset.empty: continue
        
        global_trend = check_trend_ema200(h4_subset)
        
        h4_slice_for_levels = h4_subset.tail(100)
        h4_levels = identify_levels(h4_slice_for_levels, window=10)
        
        current_price = current_m15_row['close']
        LEVEL_TOLERANCE = 5.0
        
        nearby_support = [l for l in h4_levels if l['type'] == 'SUPPORT' and abs(l['price'] - current_price) < LEVEL_TOLERANCE]
        nearby_resistance = [l for l in h4_levels if l['type'] == 'RESISTANCE' and abs(l['price'] - current_price) < LEVEL_TOLERANCE]
        
        direction = None
        if global_trend == "UP" and nearby_support: direction = "BUY"
        elif global_trend == "DOWN" and nearby_resistance: direction = "SELL"
        
        if not direction:
            if nearby_support: direction = "BUY"
            elif nearby_resistance: direction = "SELL"
            else: continue
            
        # 2. Pattern (Optional)
        # We skip explicit pattern check logic here to strictly test entry performance 
        # as per "Optimized" logic where pattern or candle is enough.
        # But we assume the base is ready.
        
        # 3. Entry
        last_m15 = df_m15.iloc[i]
        prev_m15 = df_m15.iloc[i-1]
        prev_2_m15 = df_m15.iloc[i-2]
        
        candlesticks = check_candlestick_patterns(last_m15, prev_m15, prev_2_m15)
        
        entry_signal = False
        
        if direction == "BUY":
            # Candle Filter
            has_valid_candle = any(p in candlesticks for p in candle_types["BUY"])
            
            # RSI Filter
            rsi_val = last_m15.get("RSI_14", 50)
            rsi_ok = rsi_val < rsi_max
            
            # MACD Filter
            momentum_ok = True
            if use_macd:
                macd_hist = last_m15.get("MACDh_12_26_9", 0)
                prev_macd_hist = prev_m15.get("MACDh_12_26_9", 0)
                momentum_ok = macd_hist > prev_macd_hist or macd_hist > 0
                
            if has_valid_candle and rsi_ok and momentum_ok:
                entry_signal = True
                
        elif direction == "SELL":
            has_valid_candle = any(p in candlesticks for p in candle_types["SELL"])
            
            rsi_val = last_m15.get("RSI_14", 50)
            rsi_ok = rsi_val > rsi_min
            
            momentum_ok = True
            if use_macd:
                macd_hist = last_m15.get("MACDh_12_26_9", 0)
                prev_macd_hist = prev_m15.get("MACDh_12_26_9", 0)
                momentum_ok = macd_hist < prev_macd_hist or macd_hist < 0
                
            if has_valid_candle and rsi_ok and momentum_ok:
                entry_signal = True
                
        if entry_signal:
             # Simulation
             entry_price = current_price
             # ATR based SL/TP
             atr = last_m15.get("ATRr_14", entry_price * 0.002) * 1.5
             
             sl = entry_price - atr if direction == "BUY" else entry_price + atr
             tp = entry_price + (atr * 2) if direction == "BUY" else entry_price - (atr * 2)
             
             future_candles = df_m15.iloc[i+1:i+20]
             outcome = "BE"
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
             
             if outcome == "BE" and not future_candles.empty:
                 exit_price = future_candles.iloc[-1]['close']
                 if direction == "BUY": pnl = exit_price - entry_price
                 else: pnl = entry_price - exit_price
                 outcome = "CLOSE"
                 
             trades.append({"pnl": pnl, "outcome": outcome})
             
    # Stats
    total = len(trades)
    wins = len([t for t in trades if t['pnl'] > 0])
    wr = (wins / total * 100) if total > 0 else 0
    total_pnl = sum([t['pnl'] for t in trades])
    
    print(f"Trades: {total} | WR: {wr:.1f}% | PnL: {total_pnl:.2f}")
    return {"name": scenario_name, "wr": wr, "pnl": total_pnl, "trades": total}

def optimize():
    print("Loading Data...")
    data = DataHandler()
    df_h4 = data.fetch_data("XAU/USD", "H4", limit=500)
    df_m15 = data.fetch_data("XAU/USD", "M15", limit=2000)
    
    if df_h4.empty or df_m15.empty:
        print("Data Error")
        return
        
    config = {"RSI_PERIOD": 14, "EMA_FAST": 50, "EMA_SLOW": 200}
    df_h4 = calculate_indicators(df_h4, config)
    df_m15 = calculate_indicators(df_m15, config)
    
    results = []
    
    # 1. Current Optimized (Mixed)
    results.append(run_scenario(
        df_h4, df_m15, "Current (Mixed)", 
        {"BUY": ["HAMMER", "BULLISH_ENGULFING", "MORNING_STAR"], "SELL": ["SHOOTING_STAR", "BEARISH_ENGULFING", "EVENING_STAR"]},
        30, 70, True
    ))

    # 2. Strict 3-Candle Pattern (Morning/Evening Star only)
    results.append(run_scenario(
        df_h4, df_m15, "Strict 3-Candle", 
        {"BUY": ["MORNING_STAR"], "SELL": ["EVENING_STAR"]},
        30, 70, True
    ))
    
    # 3. Pin Bar Only (Hammer/Shooting Star)
    results.append(run_scenario(
        df_h4, df_m15, "Pin Bar Only", 
        {"BUY": ["HAMMER"], "SELL": ["SHOOTING_STAR"]},
        30, 70, True
    ))
    
    # 4. Strict RSI (Current Best)
    results.append(run_scenario(
        df_h4, df_m15, "Strict RSI (<60/>40)", 
        {"BUY": ["HAMMER", "BULLISH_ENGULFING", "MORNING_STAR"], "SELL": ["SHOOTING_STAR", "BEARISH_ENGULFING", "EVENING_STAR"]},
        40, 60, True
    ))

    print("\n--- SUMMARY ---")
    results.sort(key=lambda x: x['pnl'], reverse=True)
    for r in results:
        print(f"{r['name']}: PnL=${r['pnl']:.2f}, WR={r['wr']:.1f}%, Trades={r['trades']}")

if __name__ == "__main__":
    optimize()
