import time
import json
import requests
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler

# =========================
# CONFIG
# =========================
BOT_TOKEN = "8469965625:AAFSvsOKpijGV7A78yrtvQ4Hr7Dby3ulRzs"
ALERTS_FILE = "alerts.json"
CHECK_INTERVAL = 10  # seconds

alerts = {}

# =========================
# FILE STORAGE
# =========================
def load_alerts():
    global alerts
    try:
        with open(ALERTS_FILE, "r") as f:
            alerts = json.load(f)
    except:
        alerts = {}

def save_alerts():
    with open(ALERTS_FILE, "w") as f:
        json.dump(alerts, f)

# =========================
# HELPERS
# =========================
def format_price(price):
    if price < 0.0001:
        return f"{price:.10f}"
    return f"{price:.6f}"

def get_token_data(contract):
    url = f"https://api.dexscreener.com/latest/dex/tokens/{contract}"
    try:
        r = requests.get(url, timeout=10)
        data = r.json()
        if not data["pairs"]:
            return None
        pair = data["pairs"][0]
        return {
            "price": float(pair["priceUsd"]),
            "mc": float(pair.get("marketCap", 0)),
            "name": pair["baseToken"]["name"],
            "symbol": pair["baseToken"]["symbol"],
            "change5m": float(pair.get("priceChange", {}).get("m5", 0)),
            "change1h": float(pair.get("priceChange", {}).get("h1", 0)),
            "change6h": float(pair.get("priceChange", {}).get("h6", 0)),
            "change24h": float(pair.get("priceChange", {}).get("h24", 0)),
        }
    except:
        return None

# =========================
# COMMANDS
# =========================
def start(update, context):
    update.message.reply_text("Bot running ✅")

def add(update, context):
    chat_id = str(update.effective_chat.id)

    try:
        contract = context.args[0]
        value = float(context.args[1])
        mode = context.args[2]

    except:
        update.message.reply_text("Usage:\n/add contract value price\n/add contract % 1h")
        return

    token = get_token_data(contract)
    if not token:
        update.message.reply_text("Token not found")
        return

    alert = {
        "contract": contract,
        "value": value,
        "mode": mode,
        "name": token["name"],
        "symbol": token["symbol"]
    }

    alerts.setdefault(chat_id, []).append(alert)
    save_alerts()

    update.message.reply_text(f"✅ Alert added for {token['name']} ({token['symbol']})")

# =========================
# LIST ALERTS
# =========================
def list_alerts(update, context):
    chat_id = str(update.effective_chat.id)

    if chat_id not in alerts or not alerts[chat_id]:
        update.message.reply_text("No alerts set.")
        return

    for i, a in enumerate(alerts[chat_id]):
        text = f"{i+1}. {a['name']} ({a['symbol']})\n"

        if a["mode"] == "price":
            text += f"Price ≥ ${format_price(a['value'])}"
        else:
            text += f"Change ≥ {a['value']}% ({a['mode']})"

        keyboard = [[InlineKeyboardButton("❌ Delete", callback_data=f"del_{i}")]]
        update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# =========================
# DELETE BUTTON
# =========================
def button(update, context):
    query = update.callback_query
    query.answer()

    chat_id = str(query.message.chat.id)
    index = int(query.data.split("_")[1])

    try:
        alerts[chat_id].pop(index)
        save_alerts()
        query.edit_message_text("✅ Alert deleted")
    except:
        query.edit_message_text("Error deleting alert")

# =========================
# ALERT CHECK LOOP
# =========================
def check_alerts(context):
    while True:
        for chat_id, user_alerts in alerts.items():
            for alert in user_alerts[:]:
                token = get_token_data(alert["contract"])
                if not token:
                    continue

                triggered = False

                if alert["mode"] == "price":
                    if token["price"] >= alert["value"]:
                        triggered = True
                        msg = (
                            f"🚨 {token['name']} ({token['symbol']})\n"
                            f"Hit ${format_price(alert['value'])}\n"
                            f"Current: ${format_price(token['price'])}\n"
                            f"MC: ${int(token['mc']):,}"
                        )

                else:
                    change = token.get(f"change{alert['mode']}", 0)
                    if change >= alert["value"]:
                        triggered = True
                        msg = (
                            f"🚀 {token['name']} ({token['symbol']})\n"
                            f"Up {change:.2f}% ({alert['mode']})\n"
                            f"Price: ${format_price(token['price'])}"
                        )

                if triggered:
                    context.bot.send_message(chat_id=int(chat_id), text=msg)
                    user_alerts.remove(alert)
                    save_alerts()

        time.sleep(CHECK_INTERVAL)

# =========================
# MAIN
# =========================
def main():
    load_alerts()

    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("add", add))
    dp.add_handler(CommandHandler("list", list_alerts))
    dp.add_handler(CallbackQueryHandler(button))

    import threading
    threading.Thread(target=check_alerts, args=(updater,), daemon=True).start()

    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
