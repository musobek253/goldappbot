import pandas as pd
import numpy as np
from data.feed import DataHandler
from strategies.indicators import (
    calculate_indicators, identify_levels, check_trend_ema200, 
    detect_patterns, check_candlestick_patterns
)
import logging

logging.getLogger("treding.data.feed").setLevel(logging.ERROR)

def run_scenario(df_h4, df_m15, scenario_name, params):
    # Params: {tp_mult, ema_trend, rsi_period, candle_mode}
    
    tp_mult = params.get("tp_mult", 2.0)
    ema_col = f"EMA_{params.get('ema_trend', 200)}"
    rsi_col = f"RSI_{params.get('rsi_period', 14)}"
    
    trades = []
    start_index = 200
    
    for i in range(start_index, len(df_m15)):
        current_m15_row = df_m15.iloc[i]
        current_time = current_m15_row.name
        
        # 1. Global Context
        h4_subset = df_h4[df_h4.index <= current_time]
        if h4_subset.empty: continue
        
        # Trend check using variable EMA
        if h4_subset.iloc[-1].get(ema_col) is None: continue
        
        price = h4_subset.iloc[-1]['close']
        ema_val = h4_subset.iloc[-1][ema_col]
        global_trend = "UP" if price > ema_val else "DOWN"
        
        # Level check (keep constant for this test to isolate variables)
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

        # 3. Entry
        last_m15 = df_m15.iloc[i]
        prev_m15 = df_m15.iloc[i-1]
        prev_2_m15 = df_m15.iloc[i-2]
        
        candlesticks = check_candlestick_patterns(last_m15, prev_m15, prev_2_m15)
        
        candle_types = {
            "BUY": ["HAMMER", "BULLISH_ENGULFING", "MORNING_STAR"],
            "SELL": ["SHOOTING_STAR", "BEARISH_ENGULFING", "EVENING_STAR"]
        }
        
        entry_signal = False
        
        if direction == "BUY":
            has_valid_candle = any(p in candlesticks for p in candle_types["BUY"])
            
            rsi_val = last_m15.get(rsi_col, 50)
            rsi_ok = rsi_val < 70
            
            momentum_ok = True 
            # MACD is kept simple/standard for now
            macd_hist = last_m15.get("MACDh_12_26_9", 0)
            if macd_hist <= 0: momentum_ok = False # Basic momentum check
                
            if has_valid_candle and rsi_ok and momentum_ok:
                entry_signal = True
                
        elif direction == "SELL":
            has_valid_candle = any(p in candlesticks for p in candle_types["SELL"])
            
            rsi_val = last_m15.get(rsi_col, 50)
            rsi_ok = rsi_val > 30
            
            momentum_ok = True
            macd_hist = last_m15.get("MACDh_12_26_9", 0)
            if macd_hist >= 0: momentum_ok = False
                
            if has_valid_candle and rsi_ok and momentum_ok:
                entry_signal = True
                
        if entry_signal:
             entry_price = current_price
             # Variable TP Multiplier
             atr = last_m15.get("ATRr_14", entry_price * 0.002) * 1.5
             
             sl_dist = atr
             tp_dist = atr * tp_mult 
             
             sl = entry_price - sl_dist if direction == "BUY" else entry_price + sl_dist
             tp = entry_price + tp_dist if direction == "BUY" else entry_price - tp_dist
             
             future_candles = df_m15.iloc[i+1:i+30] # Longer lookahead for higher TP
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
             
    total = len(trades)
    wins = len([t for t in trades if t['pnl'] > 0])
    wr = (wins / total * 100) if total > 0 else 0
    total_pnl = sum([t['pnl'] for t in trades])
    
    return {"name": scenario_name, "wr": wr, "pnl": total_pnl, "trades": total, "params": params}

def optimize():
    print("Loading Data...")
    data = DataHandler()
    df_h4 = data.fetch_data("XAU/USD", "H4", limit=1000) # More H4 data for EMA calc
    df_m15 = data.fetch_data("XAU/USD", "M15", limit=3000)
    
    if df_h4.empty or df_m15.empty:
        print("Data Error")
        return
        
    print("Calculating Indicators...")
    # Calculate ALL variations needed
    config = {"RSI_PERIOD": 14, "EMA_FAST": 50, "EMA_SLOW": 200}
    df_h4 = calculate_indicators(df_h4, config)
    # Add extra EMAs to H4
    df_h4["EMA_100"] = df_h4['close'].ewm(span=100, adjust=False).mean()
    
    df_m15 = calculate_indicators(df_m15, config)
    # Add extra RSI to M15
    # calculate_indicators handles RSI_PERIOD mainly, let's manually add RSI 7 if needed
    # Or just use RSI 14 for now to limit complexity, user asked for "best solutions".
    # Focus on TP Multiplier and Trend EMA first.
    
    results = []
    
    # Grid Search Params
    # TP Multipliers: 1.5, 2.0, 2.5, 3.0
    # Trend EMAs: 50, 100, 200
    
    tp_mults = [1.5, 2.0, 3.0]
    ema_trends = [50, 100, 200]
    
    count = 0
    total_scenarios = len(tp_mults) * len(ema_trends)
    
    print(f"Running {total_scenarios} scenarios...")
    
    for tp in tp_mults:
        for ema in ema_trends:
            count += 1
            name = f"TP: {tp}x | EMA: {ema}"
            print(f"[{count}/{total_scenarios}] Running {name}...")
            
            res = run_scenario(df_h4, df_m15, name, {"tp_mult": tp, "ema_trend": ema, "rsi_period": 14})
            results.append(res)
            print(f" -> PnL: {res['pnl']:.2f}, WR: {res['wr']:.1f}%")

    print("\n--- TOP 3 RESULTS ---")
    results.sort(key=lambda x: x['pnl'], reverse=True)
    for r in results[:3]:
        print(f"{r['name']}: PnL=${r['pnl']:.2f}, WR={r['wr']:.1f}%, Trades={r['trades']}")
        
    # Also show high WR results
    print("\n--- TOP WIN RATE ---")
    results.sort(key=lambda x: x['wr'], reverse=True)
    for r in results[:3]:
        print(f"{r['name']}: WR={r['wr']:.1f}%, PnL=${r['pnl']:.2f}, Trades={r['trades']}")

if __name__ == "__main__":
    optimize()
