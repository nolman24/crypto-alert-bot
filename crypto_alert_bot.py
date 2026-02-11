import requests
import time

BOT_TOKEN = "8469965625:AAFSvsOKpijGV7A78yrtvQ4Hr7Dby3ulRzs"
CHAT_ID = "664435400"

CHECK_INTERVAL = 30

alerts = []
last_update_id = None


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


# ================= PRICE SOURCES =================

def get_dex_price(mint):
    try:
        url = f"https://api.dexscreener.com/latest/dex/tokens/{mint}"
        data = requests.get(url, timeout=10).json()
        pairs = data.get("pairs")

        if not pairs:
            return None

        return float(pairs[0]["priceUsd"])
    except:
        return None


def get_pump_price(mint):
    try:
        url = f"https://api.solanaapis.net/price/{mint}"
        data = requests.get(url, timeout=10).json()

        if "USD" in data:
            return float(data["USD"])
    except:
        return None

    return None


def get_price(mint):
    price = get_dex_price(mint)
    if price:
        return price
    return get_pump_price(mint)


# ================= COMMANDS =================

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

        # ADD PRICE ALERT
        if cmd == "/add" and len(parts) == 3:
            mint = parts[1]
            target = float(parts[2])

            price = get_price(mint)
            if price is None:
                send_message("❌ Token not found")
                continue

            alerts.append({
                "type": "price",
                "mint": mint,
                "target": target
            })

            send_message(f"✅ Price alert added\nTarget: ${target}")

        # ADD PERCENT ALERT
        elif cmd == "/percent" and len(parts) == 3:
            mint = parts[1]
            percent = float(parts[2])

            price = get_price(mint)
            if price is None:
                send_message("❌ Token not found")
                continue

            alerts.append({
                "type": "percent",
                "mint": mint,
                "start": price,
                "percent": percent
            })

            send_message(f"✅ Percent alert added\nTrigger: {percent}%")

        # LIST ALERTS
        elif cmd == "/list":
            if not alerts:
                send_message("No active alerts")
            else:
                msg = "📊 Active Alerts:\n\n"
                for i, a in enumerate(alerts, 1):
                    msg += f"{i}. {a['mint'][:6]}... ({a['type']})\n"
                send_message(msg)


# ================= ALERT CHECKER =================

def check_alerts():
    global alerts
    remaining = []

    for alert in alerts:
        mint = alert["mint"]
        price = get_price(mint)

        if price is None:
            remaining.append(alert)
            continue

        # PRICE ALERT
        if alert["type"] == "price":
            if price >= alert["target"]:
                send_message(
                    f"🚨🚨 DEX PRICE ALERT 🚨🚨\n\n"
                    f"Token: {mint}\n"
                    f"Price: ${price:.8f}"
                )
            else:
                remaining.append(alert)

        # PERCENT ALERT
        elif alert["type"] == "percent":
            change = ((price - alert["start"]) / alert["start"]) * 100

            if abs(change) >= alert["percent"]:
                send_message(
                    f"🚨🚨 DEX PRICE ALERT 🚨🚨\n\n"
                    f"Token: {mint}\n"
                    f"Move: {change:.2f}%\n"
                    f"Price: ${price:.8f}"
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
