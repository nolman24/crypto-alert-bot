import os
import requests
import time
import threading
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

alerts = {}


# =========================
# FETCH DATA FROM DEXSCREENER
# =========================
def get_token_data(address):
    url = f"https://api.dexscreener.com/latest/dex/tokens/{address}"

    try:
        r = requests.get(url, timeout=10)
        data = r.json()

        if "pairs" not in data:
            return None

        pair = data["pairs"][0]

        return {
            "name": pair["baseToken"]["name"],
            "symbol": pair["baseToken"]["symbol"],
            "price": float(pair["priceUsd"]),
            "market_cap": pair.get("fdv", 0),
            "change_5m": pair["priceChange"].get("m5", "N/A"),
            "change_1h": pair["priceChange"].get("h1", "N/A"),
            "change_6h": pair["priceChange"].get("h6", "N/A"),
            "change_24h": pair["priceChange"].get("h24", "N/A"),
            "chart": pair["url"],
        }

    except:
        return None


# =========================
# COMMANDS
# =========================
async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        address = context.args[0]
        target = float(context.args[1])

        alerts[address] = target

        await update.message.reply_text("✅ Alert added!")

    except:
        await update.message.reply_text("Usage:\n/add CONTRACT_ADDRESS PRICE")


async def list_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not alerts:
        await update.message.reply_text("No active alerts.")
        return

    msg = "📋 Active Alerts:\n\n"
    for addr, price in alerts.items():
        msg += f"{addr[:6]}... → ${price}\n"

    await update.message.reply_text(msg)


async def remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        address = context.args[0]
        alerts.pop(address, None)
        await update.message.reply_text("❌ Alert removed.")
    except:
        await update.message.reply_text("Usage:\n/remove CONTRACT_ADDRESS")


# =========================
# ALERT MONITOR LOOP
# =========================
def monitor():
    print("Price alert monitor started...")

    while True:
        for addr, target_price in list(alerts.items()):
            data = get_token_data(addr)
            if not data:
                continue

            if data["price"] >= target_price:
                message = f"""
🚨🚨 DEX PRICE ALERT 🚨🚨

{data['name']} ({data['symbol']}) went above ${target_price}

Current Price: ${data['price']:.8f}
Market Cap: ${data['market_cap']:,}

Change (from DexScreener):
5 min: {data['change_5m']}%
1 hr: {data['change_1h']}%
6 hr: {data['change_6h']}%
24 hr: {data['change_24h']}

📈 Chart:
{data['chart']}
"""

                requests.post(
                    f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                    json={
                        "chat_id": CHAT_ID,
                        "text": message,
                        "disable_web_page_preview": True,
                    },
                )

                alerts.pop(addr, None)

        time.sleep(15)


# =========================
# START BOT
# =========================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("list", list_alerts))
    app.add_handler(CommandHandler("remove", remove))

    threading.Thread(target=monitor, daemon=True).start()

    print("Bot running...")
    app.run_polling()


if __name__ == "__main__":
    main()
