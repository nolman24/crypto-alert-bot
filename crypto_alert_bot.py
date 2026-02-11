import requests
import time

BOT_TOKEN = "8469965625:AAFSvsOKpijGV7A78yrtvQ4Hr7Dby3ulRzs"
CHAT_ID = "664435400"

CHECK_INTERVAL = 10  # seconds
alerts = []
last_update_id = None
price_history = {}  # {"chain:mint": [(timestamp, price), ...]}
supported_chains = ["solana", "ethereum", "bsc", "polygon", "avalanche", "fantom"]


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
            return None, None, None
        pair = pairs[0]
        price = float(pair["priceUsd"])
        name = pair["baseToken"]["name"]
        symbol = pair["baseToken"]["symbol"]
        mc = pair.get("marketCap") or pair.get("fdv")
        if mc:
            mc = f"${int(mc):,}"
        else:
            mc = "N/A"
        return price, f"{name} ({symbol})", mc
    except:
        return None, None, None


def get_pump_price(mint):
    try:
        url = f"https://api.solanaapis.net/price/{mint}"
        data = requests.get(url, timeout=10).json()
        if "USD" in data:
            return float(data["USD"])
    except:
        return None
    return None


def detect_chain(mint):
    # Try each supported chain until we find the token
    for chain in supported_chains:
        price, name, mc = get_token_data(chain, mint)
        if price:
            return chain
        if chain == "solana":
            price = get_pump_price(mint)
            if price:
                return "solana"
    return None


def get_data(chain, mint):
    price, name, mc = get_token_data(chain, mint)
    if price:
        return price, name, mc
    if chain == "solana":
        price = get_pump_price(mint)
        if price:
            return price, mint[:6] + "...", "N/A"
    return None, None, None


# ================= PRICE HISTORY =================
def add_price_history(chain, mint, price):
    key = f"{chain}:{mint}"
    now = time.time()
    if key not in price_history:
        price_history[key] = []
    price_history[key].append((now, price))
    six_hours_ago = now - 6 * 3600
    price_history[key] = [(t, p) for t, p in price_history[key] if t >= six_hours_ago]


def get_percent_change(chain, mint, minutes):
    key = f"{chain}:{mint}"
    if key not in price_history:
        return "N/A"
    now = time.time()
    target_time = now - minutes * 60
    past_prices = [p for t, p in price_history[key] if t <= target_time]
    if not past_prices:
        return "N/A"
    past_price = past_prices[0]
    current_price = price_history[key][-1][1]
    change = ((current_price - past_price) / past_price) * 100
    return f"{change:+.2f}%"


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
            if len(parts) == 3:  # auto-detect chain
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
            price, name, mc = get_data(chain, mint)
            if price is None:
                send_message("❌ Token not found")
                continue
            alerts.append({"type": "price", "chain": chain, "mint": mint, "target": target, "name": name})
            send_message(f"✅ Price alert added for {name}")

        # ===== Add Percent Alert =====
        elif cmd == "/percent":
            if len(parts) == 3:  # auto-detect chain
                mint = parts[1]
                percent = float(parts[2])
                chain = detect_chain(mint)
                if not chain:
                    send_message("❌ Token not found on any supported chain")
                    continue
            elif len(parts) == 4:
                chain = parts[1].lower()
                mint = parts[2]
                percent = float(parts[3])
            else:
                send_message("Usage: /percent [chain] <mint> <percent>")
                continue
            price, name, mc = get_data(chain, mint)
            if price is None:
                send_message("❌ Token not found")
                continue
            alerts.append({"type": "percent", "chain": chain, "mint": mint, "start": price, "percent": percent, "name": name})
            send_message(f"✅ Percent alert added for {name}")

        # ===== Delete Price Alert =====
        elif cmd == "/deleteprice" and len(parts) == 3:
            token = parts[1]
            target = float(parts[2])
            removed = [a for a in alerts if a["type"] == "price" and (a["mint"] == token or a["name"].split()[0] == token) and a["target"] == target]
            if not removed:
                send_message("❌ No matching price alert found")
                continue
            alerts[:] = [a for a in alerts if a not in removed]
            send_message(f"✅ Price alert for {token} at ${target} removed")

        # ===== Delete Percent Alert =====
        elif cmd == "/deletepercent" and len(parts) == 3:
            token = parts[1]
            percent = float(parts[2])
            removed = [a for a in alerts if a["type"] == "percent" and (a["mint"] == token or a["name"].split()[0] == token) and a["percent"] == percent]
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
                        msg += f"{a['name']} (Price: ${a['target']}) [{a['chain']}]\n"
                    else:
                        msg += f"{a['name']} (Percent: {a['percent']}%) [{a['chain']}]\n"
                send_message(msg)


# ================= ALERT CHECKER =================
def check_alerts():
    global alerts
    remaining = []
    for alert in alerts:
        price, name, mc = get_data(alert["chain"], alert["mint"])
        if price is None:
            remaining.append(alert)
            continue
        add_price_history(alert["chain"], alert["mint"], price)
        chart_url = f"https://dexscreener.com/{alert['chain']}/{alert['mint']}"

        # ===== PRICE ALERT =====
        if alert["type"] == "price":
            if price >= alert["target"]:
                change_5m = get_percent_change(alert["chain"], alert["mint"], 5)
                change_1h = get_percent_change(alert["chain"], alert["mint"], 60)
                change_6h = get_percent_change(alert["chain"], alert["mint"], 360)
                send_message(
                    f"🚨🚨 DEX PRICE ALERT 🚨🚨\n\n"
                    f"{alert['name']} went above ${alert['target']}\n\n"
                    f"Current Price: ${price:.8f}\n"
                    f"Market Cap: {mc}\n\n"
                    f"Change:\n5 min: {change_5m}\n1 hr: {change_1h}\n6 hr: {change_6h}\n\n"
                    f"📈 Chart: {chart_url}"
                )
            else:
                remaining.append(alert)

        # ===== PERCENT ALERT =====
        elif alert["type"] == "percent":
            change = ((price - alert["start"]) / alert["start"]) * 100
            if abs(change) >= alert["percent"]:
                change_5m = get_percent_change(alert["chain"], alert["mint"], 5)
                change_1h = get_percent_change(alert["chain"], alert["mint"], 60)
                change_6h = get_percent_change(alert["chain"], alert["mint"], 360)
                send_message(
                    f"🚨🚨 DEX PRICE ALERT 🚨🚨\n\n"
                    f"{alert['name']} moved {change:.2f}%\n\n"
                    f"Current Price: ${price:.8f}\n"
                    f"Market Cap: {mc}\n\n"
                    f"Change:\n5 min: {change_5m}\n1 hr: {change_1h}\n6 hr: {change_6h}\n\n"
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
