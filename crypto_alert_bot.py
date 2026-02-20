import os
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

alerts = {}

DEX_API = "https://api.dexscreener.com/latest/dex/tokens/"


# ---------- PRICE FORMAT ----------
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


# ---------- MONITOR LOOP ----------
async def monitor(context: ContextTypes.DEFAULT_TYPE):
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

            await context.bot.send_message(
                chat_id=CHAT_ID,
                text=msg,
                disable_web_page_preview=True
            )


# ---------- COMMANDS ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Alert bot running")


async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        address = context.args[0]
        price = float(context.args[1])

        token = get_token_data(address)
        if not token:
            await update.message.reply_text("❌ Token not found")
            return

        alerts[address] = {
            "price": price,
            "triggered": False
        }

        await update.message.reply_text(
            f"✅ Alert added for {token['name']} ({token['symbol']})"
        )
    except:
        await update.message.reply_text("Usage: /add <token_address> <price>")


async def list_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not alerts:
        await update.message.reply_text("No active alerts")
        return

    msg = "📊 Active Alerts:\n\n"

    for addr, data in alerts.items():
        token = get_token_data(addr)
        if token:
            msg += f"{token['name']} — ${format_price(data['price'])}\n"

    await update.message.reply_text(msg)


# ---------- MAIN ----------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("list", list_alerts))

    app.job_queue.run_repeating(monitor, interval= 8, first= 3)

    app.run_polling()


if __name__ == "__main__":
    main()
