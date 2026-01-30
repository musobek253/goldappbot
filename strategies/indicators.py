import pandas as pd
import numpy as np

def calculate_indicators(df: pd.DataFrame, config: dict = None) -> pd.DataFrame:
    """
    Faqat pandas/numpy kutubxonalaridan foydalanib, texnik indikatorlarni hisoblaydi.
    
    Argumentlar:
        df: 'open', 'high', 'low', 'close', 'volume' ustunlariga ega DataFrame.
        config: Sozlamalar lug'ati.
    """
    if config is None:
        config = {}

    close = df['close']

    # --- EMA ---
    ema_fast_len = int(config.get("EMA_FAST", 50))
    ema_slow_len = int(config.get("EMA_SLOW", 200))

    df[f"EMA_{ema_fast_len}"] = close.ewm(span=ema_fast_len, adjust=False).mean()
    df[f"EMA_{ema_slow_len}"] = close.ewm(span=ema_slow_len, adjust=False).mean()

    # --- RSI ---
    rsi_len = int(config.get("RSI_PERIOD", 14))
    
    # RSI uchun Wilder smoothing uslubi (TA-Lib kutubxonasiga eng yaqin va aniq usul)
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -1 * delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1/rsi_len, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/rsi_len, adjust=False).mean()
    
    rs = avg_gain / avg_loss
    df[f"RSI_{rsi_len}"] = 100 - (100 / (1 + rs))

    # --- MACD ---
    macd_fast = int(config.get("MACD_FAST", 12))
    macd_slow = int(config.get("MACD_SLOW", 26))
    macd_signal = int(config.get("MACD_SIGNAL", 9))

    ema_fast = close.ewm(span=macd_fast, adjust=False).mean()
    ema_slow = close.ewm(span=macd_slow, adjust=False).mean()
    df[f"MACD_{macd_fast}_{macd_slow}_{macd_signal}"] = ema_fast - ema_slow # MACD liniyasi
    df[f"MACDs_{macd_fast}_{macd_slow}_{macd_signal}"] = df[f"MACD_{macd_fast}_{macd_slow}_{macd_signal}"].ewm(span=macd_signal, adjust=False).mean() # Signal liniyasi
    df[f"MACDh_{macd_fast}_{macd_slow}_{macd_signal}"] = df[f"MACD_{macd_fast}_{macd_slow}_{macd_signal}"] - df[f"MACDs_{macd_fast}_{macd_slow}_{macd_signal}"] # Gistogramma

    # --- Bollinger Bands ---
    bb_len = int(config.get("BB_LENGTH", 20))
    bb_std_dev = float(config.get("BB_STD", 2.0))
    
    sma = close.rolling(window=bb_len).mean()
    std = close.rolling(window=bb_len).std()
    
    df[f"BBL_{bb_len}_{bb_std_dev}"] = sma - (std * bb_std_dev) # Pastki chegara
    df[f"BBM_{bb_len}_{bb_std_dev}"] = sma # O'rta (SMA)
    df[f"BBU_{bb_len}_{bb_std_dev}"] = sma + (std * bb_std_dev) # Yuqori chegara

    # --- Fibonacci Retracement ---
    # Oxirgi High/Low (yuqori/past) darajalarga asoslangan (odatiy holatda 100 ta sham)
    period = 100
    rolling_high = df['high'].rolling(window=period).max()
    rolling_low = df['low'].rolling(window=period).min()
    diff = rolling_high - rolling_low

    df["FIB_0.0"] = rolling_low
    df["FIB_0.236"] = rolling_low + (diff * 0.236)
    df["FIB_0.382"] = rolling_low + (diff * 0.382)
    df["FIB_0.5"] = rolling_low + (diff * 0.5)
    df["FIB_0.618"] = rolling_low + (diff * 0.618)
    df["FIB_0.786"] = rolling_low + (diff * 0.786)
    df["FIB_1.0"] = rolling_high

    return df

def identify_levels(df: pd.DataFrame, window=10) -> list:
    """
    Support va Resistance darajalarini aniqlaydi (Fractals / Swing High-Low).
    """
    levels = []
    # Oddiy fractal method: High[i] > High[i-2]...High[i+2]
    # Sodda versiyasi: Rolling max/min
    for i in range(window, len(df) - window):
        is_pivot_high = True
        is_pivot_low = True
        
        for j in range(1, window + 1):
            if df['high'].iloc[i] <= df['high'].iloc[i-j] or df['high'].iloc[i] <= df['high'].iloc[i+j]:
                is_pivot_high = False
            if df['low'].iloc[i] >= df['low'].iloc[i-j] or df['low'].iloc[i] >= df['low'].iloc[i+j]:
                is_pivot_low = False
        
        if is_pivot_high:
            levels.append({'type': 'RESISTANCE', 'price': df['high'].iloc[i], 'index': i})
        if is_pivot_low:
            levels.append({'type': 'SUPPORT', 'price': df['low'].iloc[i], 'index': i})
            
    return levels

def is_downtrend(df: pd.DataFrame) -> bool:
    """
    Trendni aniqlaydi. Oddiy usul: SMA 50 < SMA 200 yoki High larning pasayib borishi.
    Golden Gate strategiyasi uchun: Narx trend chizig'i ostida bo'lishi kerak.
    Biz bu yerda sodda qilib oxirgi 50 ta sham ichida High lar pasayib borayotganini tekshiramiz.
    """
    # So'nggi 50 ta sham
    recent = df.tail(50)
    # Eng oddiy test: EMA 50 < EMA 200
    if recent['EMA_50'].iloc[-1] < recent['EMA_200'].iloc[-1]:
       return True
    return False

def check_pin_bar(row) -> bool:
    """
    Shamchada Pin Bar (uzun dumli) borligini tekshiradi (Buy uchun pastki dum uzun).
    """
    body_size = abs(row['close'] - row['open'])
    total_size = row['high'] - row['low']
    
    if total_size == 0: return False
    
    lower_wick = min(row['close'], row['open']) - row['low']
    upper_wick = row['high'] - max(row['close'], row['open'])
    
    # Buy Pin Bar shartlari:
    # 1. Pastki dum tana va yuqori dumdan kamida 2 barobar katta
    # 2. Tana umumiy shamning 30% dan kichik (yoki moslash mumkin)
    
    is_pin_bar_tail = lower_wick > (body_size + upper_wick) * 2
    small_body = body_size < (total_size * 0.3)
    
    return is_pin_bar_tail and small_body

def check_trend_ema200(df: pd.DataFrame) -> str:
    """
    Check Global Trend based on EMA 200.
    Returns: "UP", "DOWN", or "NEUTRAL".
    """
    if df.empty: return "NEUTRAL"
    current_price = df['close'].iloc[-1]
    ema_200 = df['EMA_200'].iloc[-1]
    
    if current_price > ema_200:
        return "UP"
    elif current_price < ema_200:
        return "DOWN"
    return "NEUTRAL"

def check_candlestick_patterns(row, prev_row=None, prev_row_2=None) -> list:
    """
    Detects Hammer, Shooting Star, Bullish/Bearish Engulfing, Morning/Evening Star.
    Returns a list of detected pattern names.
    """
    patterns = []
    
    # 1. Hammer / Shooting Star (Pin Bar logic)
    body_size = abs(row['close'] - row['open'])
    total_size = row['high'] - row['low']
    if total_size == 0: return patterns
    
    lower_wick = min(row['close'], row['open']) - row['low']
    upper_wick = row['high'] - max(row['close'], row['open'])
    
    # Hammer (Bullish Pin Bar)
    if lower_wick > (body_size * 2) and upper_wick < body_size:
        patterns.append("HAMMER")
        
    # Shooting Star (Bearish Pin Bar)
    if upper_wick > (body_size * 2) and lower_wick < body_size:
        patterns.append("SHOOTING_STAR")
        
    # 2. Engulfing
    if prev_row is not None:
        prev_body = abs(prev_row['close'] - prev_row['open'])
        # Bullish Engulfing: Previous Red, Current Green, Current Body > Previous Body, Current completely engulfs previous
        if (prev_row['close'] < prev_row['open']) and (row['close'] > row['open']):
            if row['close'] > prev_row['open'] and row['open'] < prev_row['close']:
                 patterns.append("BULLISH_ENGULFING")
        
        # Bearish Engulfing
        if (prev_row['close'] > prev_row['open']) and (row['close'] < row['open']):
             if row['close'] < prev_row['open'] and row['open'] > prev_row['close']:
                 patterns.append("BEARISH_ENGULFING")

    # 3. Morning Star / Evening Star (3 candles)
    if prev_row is not None and prev_row_2 is not None:
        # Morning Star (Bullish Reversal)
        # 1. Long Red (prev_row_2)
        # 2. Small Body (prev_row)
        # 3. Green Candle (row) closes > 50% of 1st candle body
        
        c1_body = abs(prev_row_2['close'] - prev_row_2['open'])
        c2_body = abs(prev_row['close'] - prev_row['open'])
        c3_body = abs(row['close'] - row['open'])
        
        is_c1_red = prev_row_2['close'] < prev_row_2['open']
        is_c2_small = c2_body < (c1_body * 0.4) # Small body relative to first
        is_c3_green = row['close'] > row['open']
        
        c1_midpoint = prev_row_2['open'] - (c1_body / 2) # Open is high for red candle
        
        if is_c1_red and is_c2_small and is_c3_green:
            if row['close'] > c1_midpoint:
                patterns.append("MORNING_STAR")

        # Evening Star (Bearish Reversal)
        # 1. Long Green (prev_row_2)
        # 2. Small Body
        # 3. Red Candle (row) closes < 50% of 1st candle
        
        is_c1_green = prev_row_2['close'] > prev_row_2['open']
        # is_c2_small is same
        is_c3_red = row['close'] < row['open']
        
        c1_midpoint = prev_row_2['open'] + (c1_body / 2) # Open is low for green candle
        
        if is_c1_green and is_c2_small and is_c3_red:
            if row['close'] < c1_midpoint:
                patterns.append("EVENING_STAR")

    return patterns

def detect_patterns(df: pd.DataFrame) -> list:
    """
    Simple Pattern Recognition (Double Bottom/Top).
    Uses last 50 candles to find macro patterns.
    """
    patterns = []
    # Identify swing points
    swings = identify_levels(df, window=3) # More sensitive for patterns
    
    # Needs at least 4 swing points to form W or M
    if len(swings) < 4:
        return patterns
        
    # Logic for Double Bottom (W) - Bullish
    # Low1 -> High -> Low2 (approx equal to Low1) -> Breakout High
    lows = [s for s in swings if s['type'] == 'SUPPORT']
    if len(lows) >= 2:
        l1 = lows[-2]
        l2 = lows[-1]
        
        # Check if Lows are close (within 0.1% price tolerance)
        avg_price = (l1['price'] + l2['price']) / 2
        diff = abs(l1['price'] - l2['price'])
        
        if diff < (avg_price * 0.001):
             # Check if this is recent
             if l2['index'] > len(df) - 20: 
                 patterns.append("DOUBLE_BOTTOM")

    # Logic for Double Top (M) - Bearish
    highs = [s for s in swings if s['type'] == 'RESISTANCE']
    if len(highs) >= 2:
        h1 = highs[-2]
        h2 = highs[-1]
        
        avg_price = (h1['price'] + h2['price']) / 2
        diff = abs(h1['price'] - h2['price'])
        
        if diff < (avg_price * 0.001):
            if h2['index'] > len(df) - 20:
                patterns.append("DOUBLE_TOP")
                
    return patterns
