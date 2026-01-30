import yfinance as yf
import pandas as pd
import logging
import os
import requests
import time

# Asosiy loggingni sozlash
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DataHandler:
    def __init__(self, source="yfinance"):
        self.source = source
        self._price_cache = {} # {simbol: (narx, vaqt)}
        # API kalitini muhit o'zgaruvchilaridan yuklash
        self.goldapi_key = os.getenv("GOLDAPI_KEY")

    def fetch_data(self, symbol: str, timeframe: str, limit: int = 100) -> pd.DataFrame:
        if self.source == "yfinance":
            return self._fetch_yfinance(symbol, timeframe, limit)
        return pd.DataFrame()

    def _fetch_yfinance(self, symbol: str, timeframe: str, limit: int) -> pd.DataFrame:
        yf_symbol_map = {
            "XAU/USD": "GC=F",
            "EUR/USD": "EURUSD=X",
            "BTC/USD": "BTC-USD"
        }
        yf_symbol = yf_symbol_map.get(symbol, symbol)

        yf_tf_map = {
            "M1": "1m", "M5": "5m", "M15": "15m", "M30": "30m",
            "H1": "1h", "H4": "1h", "D1": "1d"
        }
        interval = yf_tf_map.get(timeframe, "1d")
        
        period = "5d" 
        if timeframe in ["D1", "H4"]:
            period = "2y" # Context uchun ko'proq tarix
        elif timeframe in ["H1", "M15", "M30"]:
            period = "60d" # Yahoo Finance intraday limiti (15m uchun max ~60 kun)
        
        try:
            df = yf.download(yf_symbol, interval=interval, period=period, progress=False, auto_adjust=True)
            if df.empty:
                logger.warning(f"{yf_symbol} uchun ma'lumot topilmadi")
                return pd.DataFrame()
            
            if isinstance(df.columns, pd.MultiIndex):
                 df.columns = df.columns.droplevel(1)

            df.columns = [c.lower() for c in df.columns]
            
            # Agar M1 bo'lsa va kesh bo'sh yoki 15 soniyadan eski bo'lsa, keshni yangilash
            if timeframe == "M1" and not df.empty:
                curr_price, ts = self._price_cache.get(symbol, (None, 0))
                if time.time() - ts > 15:
                    self._price_cache[symbol] = (float(df["close"].iloc[-1]), time.time())

            return df.tail(limit)

        except Exception as e:
            logger.error(f"yfinance dan ma'lumot olishda xatolik: {e}")
            return pd.DataFrame()

    def _fetch_goldapi_price(self, symbol: str) -> float:
        # Agar muhit o'zgaruvchisi yo'q bo'lsa, zaxira kalitdan foydalanish
        api_key = self.goldapi_key or "goldapi-c1v6w5smkzqhmbv-io"
            
        if symbol == "XAU/USD":
            url = "https://www.goldapi.io/api/XAU/USD"
            headers = {
                "x-access-token": api_key,
                "Content-Type": "application/json"
            }
            try:
                response = requests.get(url, headers=headers, timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    # Ustuvorlik: bid > price (bid - foydalanuvchilar bozor narxi sifatida ko'radigan narx)
                    price = float(data.get('price'))
                    bid = float(data.get('bid', price))
                    self._price_cache[symbol] = (bid, time.time())
                    return bid
            except Exception as e:
                logger.error(f"GoldAPI dan yuklashda xatolik: {e}")
        return None

    def get_current_price(self, symbol: str, force_fetch: bool = False) -> float:
        # Keshni tekshirish (5 soniya amal qilish muddati)
        if not force_fetch and symbol in self._price_cache:
            price, ts = self._price_cache[symbol]
            if time.time() - ts < 5:
                return float(price)

        # Oltin uchun birinchi GoldAPI ni sinab ko'rish
        if symbol == "XAU/USD":
            ga_price = self._fetch_goldapi_price(symbol)
            if ga_price:
                return ga_price

        # Zaxira sifatida yfinance
        df = self.fetch_data(symbol, "M1", limit=1)
        if not df.empty:
            price = float(df["close"].iloc[-1])
            self._price_cache[symbol] = (price, time.time())
            return price
        return 0.0
