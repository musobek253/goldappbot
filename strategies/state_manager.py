import json
import os
import time
from datetime import datetime

STATE_FILE = "trading_state.json"

def load_state():
    if not os.path.exists(STATE_FILE):
        return {"last_loss_time": 0, "active_trade": None}
    try:
        with open(STATE_FILE, "r") as f:
            data = json.load(f)
            # Ensure keys exist
            if "last_loss_time" not in data: data["last_loss_time"] = 0
            if "active_trade" not in data: data["active_trade"] = None
            return data
    except:
        return {"last_loss_time": 0, "active_trade": None}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=4)

def open_trade(symbol, direction, entry, sl, tp):
    state = load_state()
    state["active_trade"] = {
        "symbol": symbol,
        "direction": direction,
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "start_time": time.time()
    }
    save_state(state)

def update_trade_status(current_high, current_low):
    """
    Checks if active trade hit SL or TP based on candle High/Low.
    """
    state = load_state()
    trade = state.get("active_trade")
    
    if not trade:
        return

    sl = trade["sl"]
    tp = trade["tp"]
    direction = trade["direction"]
    
    # Check outcomes
    is_loss = False
    is_win = False
    
    if direction == "BUY":
        if current_low <= sl: is_loss = True
        elif current_high >= tp: is_win = True
    elif direction == "SELL":
        if current_high >= sl: is_loss = True
        elif current_low <= tp: is_win = True
        
    if is_loss:
        print(f"🛑 TRADE STOPPED OUT (LOSS). Activating 4h Cooldown.")
        state["last_loss_time"] = time.time()
        state["active_trade"] = None
        save_state(state)
    elif is_win:
        print(f"✅ TRADE WON. Clearing active trade.")
        state["active_trade"] = None
        save_state(state)

def check_cooldown(hours=4):
    """Returns (True, remaining_minutes) if in cooldown"""
    state = load_state()
    last_loss = state.get("last_loss_time", 0)
    
    if last_loss == 0:
        return False, 0
        
    cooldown_seconds = hours * 3600
    elapsed = time.time() - last_loss
    
    if elapsed < cooldown_seconds:
        remaining = int((cooldown_seconds - elapsed) / 60)
        return True, remaining
    
    return False, 0
