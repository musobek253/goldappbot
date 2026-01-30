import pandas as pd
import numpy as np
from data.feed import DataHandler
from strategies.indicators import (
    calculate_indicators, identify_levels, check_trend_ema200, 
    detect_patterns, check_candlestick_patterns
)
import logging

logging.getLogger("treding.data.feed").setLevel(logging.ERROR)

def run_scenario(df_h4, df_h1, df_m15, scenario_name, params):
    # Params: {multi_tf: bool, strict_candle: bool}
    
    use_multi_tf = params.get("multi_tf", False)
    
    trades = []
    start_index = 200
    
    cooldown_until = 0 # Index to skip until
    
    for i in range(start_index, len(df_m15)):
        if i < cooldown_until: continue
        
        current_m15_row = df_m15.iloc[i]
        current_time = current_m15_row.name
        
        # Sync H4 and H1
        h4_subset = df_h4[df_h4.index <= current_time]
        h1_subset = df_h1[df_h1.index <= current_time]
        
        if h4_subset.empty or h1_subset.empty: continue
        
        # ... (rest of logic) ...
        
        # 1. H4 Analysis
        # Trend EMA 200 (Standard)
        h4_last = h4_subset.iloc[-1]
        ema_200 = h4_last.get("EMA_200")
        if ema_200 is None: continue
        
        global_trend = "UP" if h4_last['close'] > ema_200 else "DOWN"
        
        # Levels
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

        # 2. H1 Confirmation (NEW)
        if use_multi_tf:
            h1_last = h1_subset.iloc[-1]
            h1_open = h1_last['open']
            h1_close = h1_last['close']
            
            is_h1_bullish = h1_close > h1_open
            is_h1_bearish = h1_close < h1_open
            
            # Additional Check: H4 Candle Color
            h4_open = h4_last['open']
            h4_close = h4_last['close']
            is_h4_bullish = h4_close > h4_open
            is_h4_bearish = h4_close < h4_open
            
            if direction == "BUY":
                if not (is_h1_bullish and is_h4_bullish): continue # Strict: H1 and H4 must show GREEN
            elif direction == "SELL":
                if not (is_h1_bearish and is_h4_bearish): continue # Strict: H1 and H4 must show RED

        # 3. Entry (M15)
        last_m15 = df_m15.iloc[i]
        prev_m15 = df_m15.iloc[i-1]
        prev_2_m15 = df_m15.iloc[i-2]
        
        candlesticks = check_candlestick_patterns(last_m15, prev_m15, prev_2_m15)
        
        # Standard Signals
        buy_candles = ["HAMMER", "BULLISH_ENGULFING", "MORNING_STAR"]
        sell_candles = ["SHOOTING_STAR", "BEARISH_ENGULFING", "EVENING_STAR"]
        
        entry_signal = False
        
        if direction == "BUY":
            has_candle = any(p in candlesticks for p in buy_candles)
            # RSI/MACD Standard
            rsi_ok = last_m15.get("RSI_14", 50) < 70
            macd_hist = last_m15.get("MACDh_12_26_9", 0)
            momentum_ok = macd_hist > prev_m15.get("MACDh_12_26_9", 0) or macd_hist > 0
            
            if has_candle and rsi_ok and momentum_ok:
                entry_signal = True
                
        elif direction == "SELL":
            has_candle = any(p in candlesticks for p in sell_candles)
            rsi_ok = last_m15.get("RSI_14", 50) > 30
            macd_hist = last_m15.get("MACDh_12_26_9", 0)
            momentum_ok = macd_hist < prev_m15.get("MACDh_12_26_9", 0) or macd_hist < 0
            
            if has_candle and rsi_ok and momentum_ok:
                entry_signal = True
                
        if entry_signal:
             entry_price = current_price
             atr = last_m15.get("ATRr_14", entry_price * 0.002) * 1.5
             
             # Optimal settings from previous search
             sl_dist = atr * 1.0
             tp_dist = atr * 2.0 # Total 3.0 ATR
             
             sl = entry_price - sl_dist if direction == "BUY" else entry_price + sl_dist
             tp = entry_price + tp_dist if direction == "BUY" else entry_price - tp_dist
             
             future_candles = df_m15.iloc[i+1:i+30]
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
             
             # COOLDOWN LOGIC: If Loss, skip 4 hours (16 M15 candles)
             if outcome == "LOSS":
                 cooldown_until = i + 16
             
    total = len(trades)
    wins = len([t for t in trades if t['pnl'] > 0])
    wr = (wins / total * 100) if total > 0 else 0
    total_pnl = sum([t['pnl'] for t in trades])
    
    return {"name": scenario_name, "wr": wr, "pnl": total_pnl, "trades": total}

def optimize():
    print("Loading Data...")
    data = DataHandler()
    df_h4 = data.fetch_data("XAU/USD", "H4", limit=1000)
    df_h1 = data.fetch_data("XAU/USD", "H1", limit=2000) # Added H1
    df_m15 = data.fetch_data("XAU/USD", "M15", limit=3000)
    
    if df_h4.empty or df_h1.empty or df_m15.empty:
        print("Data Error")
        return
        
    print("Calculating Indicators...")
    config = {"RSI_PERIOD": 14, "EMA_FAST": 50, "EMA_SLOW": 200}
    df_h4 = calculate_indicators(df_h4, config)
    df_h1 = calculate_indicators(df_h1, config)
    df_m15 = calculate_indicators(df_m15, config)
    
    results = []
    
    # 1. Base Strategy (No Multi-TF checks, just levels/trend)
    results.append(run_scenario(df_h4, df_h1, df_m15, "Base Strategy", {"multi_tf": False}))
    
    # 2. Multi-TF Alignment (H4+H1 Candle Colors must match M15 entry)
    results.append(run_scenario(df_h4, df_h1, df_m15, "Multi-TF Alignment (H4+H1+M15)", {"multi_tf": True}))
    
    print("\n--- RESULTS ---")
    results.sort(key=lambda x: x['pnl'], reverse=True)
    for r in results:
        print(f"{r['name']}: PnL=${r['pnl']:.2f}, WR={r['wr']:.1f}%, Trades={r['trades']}")

if __name__ == "__main__":
    optimize()
