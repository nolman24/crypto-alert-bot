import os
import requests
import time
from telegram import Bot
from telegram.ext import Updater, CommandHandler

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

bot = Bot(token=BOT_TOKEN)

alerts = {}

DEX_API = "https://api.dexscreener.com/latest/dex/tokens/"

# ---------- PRICE FORMATTER ----------
def format_price(price):
    return f"{price:.8f}".rstrip("0").rstrip(".")


# ---------- FETCH TOKEN DATA ----------
def get_token_data(address):
    try:
        r = requests.get(DEX_API + address, timeout=10)
        data = r.json()

        if not data.get("pairs"):
            return None

        pair = data["pairs"][0]

        return {
            "name": pair["baseToken"]["name"],
            "symbol": pair["baseToken"]["symbol"],
            "price": float(pair["priceUsd"]),
            "mc": int(float(pair.get("fdv", 0))),
            "chart": f"https://dexscreener.com/{pair['chainId']}/{pair['pairAddress']}"
        }

    except:
        return None


# ---------- ALERT LOOP ----------
def monitor(context):
    for addr, target in alerts.items():
        token = get_token_data(addr)
        if not token:
            continue

        price = token["price"]

        if price >= target["price"] and not target["triggered"]:
            target["triggered"] = True

            msg = (
                "🚨🚨 DEX PRICE ALERT 🚨🚨\n\n"
                f"{token['name']} ({token['symbol']}) went above ${format_price(target['price'])}\n\n"
                f"Current Price: ${format_price(price)}\n"
                f"Market Cap: ${token['mc']:,}\n\n"
                f"Chart: {token['chart']}"
            )

            bot.send_message(
                chat_id=CHAT_ID,
                text=msg,
                disable_web_page_preview=True
            )


# ---------- COMMANDS ----------
def start(update, context):
    update.message.reply_text("✅ Alert bot running")


def add(update, context):
    try:
        address = context.args[0]
        price = float(context.args[1])

        token = get_token_data(address)
        if not token:
            update.message.reply_text("❌ Token not found")
            return

        alerts[address] = {
            "price": price,
            "triggered": False
        }

        update.message.reply_text(
            f"✅ Alert added for {token['name']} ({token['symbol']})"
        )

    except:
        update.message.reply_text("Usage: /add <token_address> <price>")


def list_alerts(update, context):
    if not alerts:
        update.message.reply_text("No active alerts")
        return

    msg = "📊 Active Alerts:\n\n"

    for addr, data in alerts.items():
        token = get_token_data(addr)
        if token:
            msg += f"{token['name']} — ${format_price(data['price'])}\n"

    update.message.reply_text(msg)


# ---------- MAIN ----------
def main():
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("add", add))
    dp.add_handler(CommandHandler("list", list_alerts))

    updater.job_queue.run_repeating(monitor, interval=30, first=10)

    updater.start_polling()
    updater.idle()


if __name__ == "__main__":
    main()
