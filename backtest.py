import pandas as pd
from treding.data.feed import DataHandler
from treding.strategies.indicators import calculate_indicators
from treding.db.database import Database

def run_backtest(symbol="XAU/USD", timeframe="H1", limit=500):
    print(f"--- {symbol} uchun Backtest ishga tushirildi ({timeframe}) ---")
    
    # 1. Ma'lumotlarni yuklash
    data = DataHandler()
    df = data.fetch_data(symbol, timeframe, limit=limit)
    if df.empty:
        print("Ma'lumot topilmadi.")
        return

    # 2. Indikatorlarni qo'shish
    # Standart sozlamalardan foydalanish
    config = {"RSI_PERIOD": 14}
    df = calculate_indicators(df, config)
    
    # 3. Iteratsiya (Takrorlash)
    balance = 1000
    position = None
    trades = []
    
    # Oddiy Loop
    # Eslatma: Mantiq engine.py bilan mos bo'lishi kerak, lekin backtest uchun uni tezlashtiramiz.
    # Indikatorlar shakllanishi uchun 50-indeksdan boshlab iteratsiya qilamiz.
    for i in range(50, len(df)):
        row = df.iloc[i]
        prev_row = df.iloc[i-1]
        price = row['close']
        
        # Mantiqiy nusxa (Soddalashtirilgan)
        rsi = row.get("RSI_14")
        
        # --- Fibonacci Mantig'i ---
        fib_levels = [0.236, 0.382, 0.5, 0.618, 0.786]
        fib_signal_near = False
        for level in fib_levels:
            fib_price = row.get(f"FIB_{level}")
            if fib_price:
                if abs(price - fib_price) < (price * 0.0005): # Ruxsat etilgan farq (Tolerance)
                    fib_signal_near = True
                    break

        # --- Trend Pullback Strategiyasi ---
        # 1. Trendni aniqlash
        ema_200 = row.get("EMA_200")
        
        # 2. Pullback (qayrilish)ni aniqlash
        # Faqat o'suvchi trendda (Narx > EMA200) VA RSI past bo'lsa (masalan, < 45) sotib olish (Buy)
        # Faqat tushuvchi trendda (Narx < EMA200) VA RSI yuqori bo'lsa (masalan, > 55) sotish (Sell)
        
        if position is None:
             if ema_200 and price > ema_200 and rsi < 45: # O'suvchi trendda tushishni (dip) sotib olish
                 position = {"type": "BUY", "price": price, "time": row.name}
             elif ema_200 and price < ema_200 and rsi > 55: # Tushuvchi trendda ko'tarilishni (rally) sotish
                 position = {"type": "SELL", "price": price, "time": row.name}
        
        # CHIQISH (EXIT)
        elif position:
            pnl = 0
            closed = False
            
            # SL / TP Doimiylari
            STOP_LOSS_PRICE = 20.0 # $20 qarshi harakat
            
            pnl_curr = 0
            if position['type'] == "BUY":
                pnl_curr = price - position['price']
                # SL ni tekshirish
                if pnl_curr < -STOP_LOSS_PRICE:
                    pnl = pnl_curr
                    closed = True
                # Signal orqali chiqishni tekshirish
                elif rsi > 55:
                    pnl = pnl_curr
                    closed = True
                    
            elif position['type'] == "SELL":
                pnl_curr = position['price'] - price
                # SL ni tekshirish
                if pnl_curr < -STOP_LOSS_PRICE:
                    pnl = pnl_curr
                    closed = True
                # Signal orqali chiqishni tekshirish
                elif rsi < 45: 
                    pnl = pnl_curr
                    closed = True
            
            if closed:
                trades.append(pnl)
                balance += pnl
                position = None

    print(f"Jami savdolar: {len(trades)}")
    print(f"Yakuniy balans: {balance:.2f} (Boshlanish: 1000)")
    import numpy as np
    if trades:
        print(f"Win Rate: {np.mean([1 if t > 0 else 0 for t in trades])*100:.1f}%")

if __name__ == "__main__":
    run_backtest()
