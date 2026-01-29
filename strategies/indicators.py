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
