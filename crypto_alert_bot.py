import requests
import time

BOT_TOKEN = "8469965625:AAFSvsOKpijGV7A78yrtvQ4Hr7Dby3ulRzs"
CHAT_ID = "664435400"

CHECK_INTERVAL = 10  # seconds
alerts = []
last_update_id = None

supported_chains = ["solana", "ethereum", "bsc", "polygon", "avalanche", "fantom"]

# Mapping for DexScreener keys
TIMEFRAME_MAP = {
    "5m": "m5",
    "1h": "h1",
    "6h": "h6",
    "24h": "d1"
}


# ================= TELEGRAM =================
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
            return None, None, None, None
        pair = pairs[0]
        price = float(pair["priceUsd"])
        name = pair["baseToken"]["name"]
        symbol = pair["baseToken"]["symbol"]
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
            if len(parts) == 2 or len(parts) == 3:  # auto-detect chain
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
            alerts.append({"type": "price", "chain": chain, "mint": mint, "target": target, "name": name, "symbol": symbol})
            send_message(f"✅ Price alert added for {name} ({symbol})")

        # ===== Add Percent Alert =====
        elif cmd == "/percent":
            if len(parts) == 4:  # auto-detect chain
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
            alerts.append({
                "type": "percent",
                "chain": chain,
                "mint": mint,
                "percent": percent,
                "timeframe": timeframe,
                "name": name,
                "symbol": symbol
            })
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
            send_message(f"✅ Price alert for {token} at ${target} removed")

        # ===== Delete Percent Alert =====
        elif cmd == "/deletepercent" and len(parts) == 3:
            token = parts[1]
            percent = float(parts[2])
            removed = [a for a in alerts if a["type"] == "percent" and (a["mint"] == token or a["symbol"] == token) and a["percent"] == percent]
            if not removed:
                send_message("❌ No matching percent alert found")
                continue
            alerts[:] = [a for a in alerts if a not in removed]
            send_message(f"✅ Percent alert for {token} at {percent}% removed")

        # ===== List Alerts =====
        elif cmd == "/list":
            if not alerts:
                send_message("No active alerts")
            else:
                msg = "📊 Active Alerts:\n\n"
                for a in alerts:
                    if a["type"] == "price":
                        msg += f"{a['name']} ({a['symbol']}) - Price: ${a['target']} [{a['chain']}]\n"
                    else:
                        msg += f"{a['name']} ({a['symbol']}) - Percent: {a['percent']}% {a['timeframe']} [{a['chain']}]\n"
                send_message(msg)


# ================= ALERT CHECKER =================
def check_alerts():
    global alerts
    remaining = []
    for alert in alerts:
        price, name, symbol, mc, price_changes = get_token_data(alert["chain"], alert["mint"])
        if price is None:
            remaining.append(alert)
            continue
        chart_url = f"https://dexscreener.com/{alert['chain']}/{alert['mint']}"

        # ===== PRICE ALERT =====
        if alert["type"] == "price":
            if price >= alert["target"]:
                send_message(
                    f"🚨🚨 DEX PRICE ALERT 🚨🚨\n\n"
                    f"{name} ({symbol}) went above ${alert['target']}\n\n"
                    f"Current Price: ${price:.8f}\n"
                    f"Market Cap: {mc}\n\n"
                    f"Change (from DexScreener):\n"
                    f"5 min: {price_changes.get('m5', 'N/A')}%\n"
                    f"1 hr: {price_changes.get('h1', 'N/A')}%\n"
                    f"6 hr: {price_changes.get('h6', 'N/A')}%\n"
                    f"24 hr: {price_changes.get('d1', 'N/A')}%\n\n"
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
            # Only trigger on positive increase
            if pct_change >= alert["percent"]:
                send_message(
                    f"🚨🚨 DEX PRICE ALERT 🚨🚨\n\n"
                    f"{name} ({symbol}) moved +{pct_change:.2f}% over {alert['timeframe']}\n\n"
                    f"Current Price: ${price:.8f}\n"
                    f"Market Cap: {mc}\n\n"
                    f"Change (from DexScreener):\n"
                    f"5 min: {price_changes.get('m5', 'N/A')}%\n"
                    f"1 hr: {price_changes.get('h1', 'N/A')}%\n"
                    f"6 hr: {price_changes.get('h6', 'N/A')}%\n"
                    f"24 hr: {price_changes.get('d1', 'N/A')}%\n\n"
                    f"📈 Chart: {chart_url}"
                )
            else:
                remaining.append(alert)

    alerts = remaining


# ================= MAIN LOOP =================
while True:
    try:
        handle_commands()
        check_alerts()
        time.sleep(CHECK_INTERVAL)
    except Exception as e:
        print("Error:", e)
        time.sleep(10)
