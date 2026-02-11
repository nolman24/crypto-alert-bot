import requests
import time
import json
import os

BOT_TOKEN = "8469965625:AAFSvsOKpijGV7A78yrtvQ4Hr7Dby3ulRzs"
CHAT_ID = "664435400"

CHECK_INTERVAL = 10  # seconds
ALERTS_FILE = "alerts.json"

supported_chains = ["solana", "ethereum", "bsc", "polygon", "avalanche", "fantom"]
TIMEFRAME_MAP = {
    "5m": "m5",
    "1h": "h1",
    "6h": "h6",
    "24h": "d1"
}

# ================= LOAD/ SAVE ALERTS =================
try:
    with open(ALERTS_FILE, "r") as f:
        alerts = json.load(f)
except FileNotFoundError:
    alerts = []

def save_alerts():
    with open(ALERTS_FILE, "w") as f:
        json.dump(alerts, f)

# ================= TELEGRAM =================
last_update_id = None
def send_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": text})

def get_updates():
    global last_update_id
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    params = {"timeout": 100}
    if last_update_id:
        params["offset"] = last_update_id + 1
    res = requests.get(url, params=params).json()
    if res["result"]:
        last_update_id = res["result"][-1]["update_id"]
    return res["result"]

# ================= TOKEN DATA =================
def get_token_data(chain, mint):
    try:
        url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
        data = requests.get(url, timeout=10).json()
        pairs = data.get("pairs")
        if not pairs:
            return None, None, None, None, None
        pair = pairs[0]
        price = float(pair["priceUsd"])
        name = pair["baseToken"].get("name") or None
        symbol = pair["baseToken"].get("symbol") or None
        mc = pair.get("marketCap") or pair.get("fdv")
        if mc:
            mc = f"${int(mc):,}"
        else:
            mc = "N/A"
        price_changes = pair.get("priceChange") or {}
        return price, name, symbol, mc, price_changes
    except:
        return None, None, None, None, None

def detect_chain(mint):
    for chain in supported_chains:
        price, name, symbol, mc, price_changes = get_token_data(chain, mint)
        if price:
            return chain
    return None

# ================= FORMAT CHANGES =================
def format_changes(price_changes):
    intervals = ["m5", "h1", "h6", "d1"]
    names = {"m5": "5 min", "h1": "1 hr", "h6": "6 hr", "d1": "24 hr"}
    display = ""
    for key in intervals:
        pct = price_changes.get(key)
        if pct is not None:
            display += f"{names[key]}: {pct:.2f}%\n"
        else:
            display += f"{names[key]}: N/A\n"
    return display

def format_price(price):
    if price >= 0.0001:
        return f"${price:.8f}"
    else:
        return f"${price:.12f}".rstrip("0").rstrip(".")

# ================= COMMAND HANDLER =================
def handle_commands():
    global alerts
    updates = get_updates()
    for update in updates:
        if "message" not in update:
            continue
        text = update["message"].get("text", "")
        parts = text.split()
        if not parts:
            continue
        cmd = parts[0].lower()

        # ===== Add Price Alert =====
        if cmd == "/add":
            if len(parts) == 2 or len(parts) == 3:
                mint = parts[1]
                target = float(parts[2])
                chain = detect_chain(mint)
                if not chain:
                    send_message("❌ Token not found on any supported chain")
                    continue
            elif len(parts) == 4:
                chain = parts[1].lower()
                mint = parts[2]
                target = float(parts[3])
            else:
                send_message("Usage: /add [chain] <mint> <target>")
                continue
            price, name, symbol, mc, _ = get_token_data(chain, mint)
            if price is None:
                send_message("❌ Token not found")
                continue
            name = name or mint
            symbol = symbol or mint[:6]
            alerts.append({"type": "price", "chain": chain, "mint": mint, "target": target, "name": name, "symbol": symbol})
            save_alerts()
            send_message(f"✅ Price alert added for {name} ({symbol})")

        # ===== Add Percent Alert =====
        elif cmd == "/percent":
            if len(parts) == 4:
                mint = parts[1]
                percent = float(parts[2])
                timeframe = parts[3]
                chain = detect_chain(mint)
                if not chain:
                    send_message("❌ Token not found on any supported chain")
                    continue
            elif len(parts) == 5:
                chain = parts[1].lower()
                mint = parts[2]
                percent = float(parts[3])
                timeframe = parts[4]
            else:
                send_message("Usage: /percent [chain] <mint> <percent> <timeframe>")
                continue
            if timeframe not in TIMEFRAME_MAP:
                send_message("❌ Timeframe must be one of: 5m, 1h, 6h, 24h")
                continue
            price, name, symbol, mc, price_changes = get_token_data(chain, mint)
            if price is None:
                send_message("❌ Token not found")
                continue
            name = name or mint
            symbol = symbol or mint[:6]
            alerts.append({
                "type": "percent",
                "chain": chain,
                "mint": mint,
                "percent": percent,
                "timeframe": timeframe,
                "name": name,
                "symbol": symbol
            })
            save_alerts()
            send_message(f"✅ Percent alert added for {name} ({symbol}) ({percent}% over {timeframe})")

        # ===== Delete Price Alert =====
        elif cmd == "/deleteprice" and len(parts) == 3:
            token = parts[1]
            target = float(parts[2])
            removed = [a for a in alerts if a["type"] == "price" and (a["mint"] == token or a["symbol"] == token) and a["target"] == target]
            if not removed:
                send_message("❌ No matching price alert found")
                continue
            alerts[:] = [a for a in alerts if a not in removed]
            save_alerts()
            send_message(f"✅ Price alert for {token} at {format_price(target)} removed")

        # ===== Delete Percent Alert =====
        elif cmd == "/deletepercent" and len(parts) == 3:
            token = parts[1]
            percent = float(parts[2])
            removed = [a for a in alerts if a["type"] == "percent" and (a["mint"] == token or a["symbol"] == token) and a["percent"] == percent]
            if not removed:
                send_message("❌ No matching percent alert found")
                continue
            alerts[:] = [a for a in alerts if a not in removed]
            save_alerts()
            send_message(f"✅ Percent alert for {token} at {percent}% removed")

        # ===== Delete by Number =====
        elif cmd == "/delete" and len(parts) == 2:
            try:
                idx = int(parts[1]) - 1
                if 0 <= idx < len(alerts):
                    removed = alerts.pop(idx)
                    save_alerts()
                    send_message(f"✅ Alert #{parts[1]} ({removed['name']} {removed['symbol']}) deleted")
                else:
                    send_message("❌ Invalid alert number")
            except ValueError:
                send_message("❌ Please enter a valid number")

        # ===== List Alerts =====
        elif cmd == "/list":
            if not alerts:
                send_message("No active alerts")
            else:
                msg = "📊 Active Alerts:\n\n"
                for i, a in enumerate(alerts, 1):
                    if a["type"] == "price":
                        msg += f"{i}. {a['name']} ({a['symbol']}) - Price: {format_price(a['target'])} [{a['chain']}]\n"
                    else:
                        msg += f"{i}. {a['name']} ({a['symbol']}) - Percent: {a['percent']}% {a['timeframe']} [{a['chain']}]\n"
                send_message(msg)

# ================= CATCH-UP FOR MISSED ALERTS =================
def catch_up_alerts():
    global alerts
    for alert in alerts:
        price, name, symbol, mc, price_changes = get_token_data(alert["chain"], alert["mint"])
        if price is None:
            continue
        name = name or alert["mint"]
        symbol = symbol or alert["mint"][:6]
        chart_url = f"https://dexscreener.com/{alert['chain']}/{alert['mint']}"
        price_str = format_price(price)
        target_str = format_price(alert.get("target", price))

        if alert["type"] == "price" and price >= alert["target"]:
            send_message(
                f"🚨🚨 DEX PRICE ALERT 🚨🚨\n\n"
                f"{name} ({symbol}) went above {target_str} (triggered while bot offline)\n\n"
                f"Current Price: {price_str}\n"
                f"Market Cap: {mc}\n\n"
                f"Change (from DexScreener):\n{format_changes(price_changes)}"
                f"📈 Chart: {chart_url}"
            )

        elif alert["type"] == "percent":
            key = TIMEFRAME_MAP.get(alert["timeframe"])
            if key:
                pct_change = price_changes.get(key)
                if pct_change is not None and pct_change >= alert["percent"]:
                    send_message(
                        f"🚨🚨 DEX PRICE ALERT 🚨🚨\n\n"
                        f"{name} ({symbol}) moved +{pct_change:.2f}% over {alert['timeframe']} "
                        f"(triggered while bot offline)\n\n"
                        f"Current Price: {price_str}\n"
                        f"Market Cap: {mc}\n\n"
                        f"Change (from DexScreener):\n{format_changes(price_changes)}"
                        f"📈 Chart: {chart_url}"
                    )

# Catch up on any alerts missed during downtime
catch_up_alerts()

# ================= ALERT CHECKER =================
def check_alerts():
    global alerts
    remaining = []
    for alert in alerts:
        price, name, symbol, mc, price_changes = get_token_data(alert["chain"], alert["mint"])
        if price is None:
            remaining.append(alert)
            continue
        name = name or alert["mint"]
        symbol = symbol or alert["mint"][:6]
        chart_url = f"https://dexscreener.com/{alert['chain']}/{alert['mint']}"
        price_str = format_price(price)
        target_str = format_price(alert.get("target", price))

        # ===== PRICE ALERT =====
        if alert["type"] == "price":
            if price >= alert["target"]:
                send_message(
                    f"🚨🚨 DEX PRICE ALERT 🚨🚨\n\n"
                    f"{name} ({symbol}) went above {target_str}\n\n"
                    f"Current Price: {price_str}\n"
                    f"Market Cap: {mc}\n\n"
                    f"Change (from DexScreener):\n{format_changes(price_changes)}"
                    f"📈 Chart: {chart_url}"
                )
            else:
                remaining.append(alert)

        # ===== PERCENT ALERT =====
        elif alert["type"] == "percent":
            key = TIMEFRAME_MAP.get(alert["timeframe"])
            if not key:
                remaining.append(alert)
                continue
            pct_change = price_changes.get(key)
            if pct_change is None:
                remaining.append(alert)
                continue
            if pct_change >= alert["percent"]:
                send_message(
                    f"🚨🚨 DEX PRICE ALERT 🚨🚨\n\n"
                    f"{name} ({symbol}) moved +{pct_change:.2f}% over {alert['timeframe']}\n\n"
                    f"Current Price: {price_str}\n"
                    f"Market Cap: {mc}\n\n"
                    f"Change (from DexScreener):\n{format_changes(price_changes)}"
                    f"📈 Chart: {chart_url}"
                )
            else:
                remaining.append(alert)

    alerts = remaining
    save_alerts()

# ================= MAIN LOOP =================
while True:
    try:
        handle_commands()
        check_alerts()
        time.sleep(CHECK_INTERVAL)
    except Exception as e:
        print("Error:", e)
        time.sleep(10)
