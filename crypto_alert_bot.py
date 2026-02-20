import os
import requests
import uuid
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
)

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
            "chart": f"https://dexscreener.com/{pair['chainId']}/{pair['pairAddress']}",
            "change5m": float(pair["priceChange"].get("m5", 0)),
            "change1h": float(pair["priceChange"].get("h1", 0)),
            "change6h": float(pair["priceChange"].get("h6", 0)),
        }
    except:
        return None


# ---------- MONITOR LOOP ----------
async def monitor(context: ContextTypes.DEFAULT_TYPE):
    for alert_id, alert in list(alerts.items()):
        token = get_token_data(alert["address"])
        if not token:
            continue

        # PRICE ALERT
        if alert["type"] == "price":
            price = token["price"]

            if price >= alert["price"] and not alert["triggered"]:
                alert["triggered"] = True

                msg = (
                    "🚨🚨 DEX PRICE ALERT 🚨🚨\n\n"
                    f"{token['name']} ({token['symbol']}) crossed ${format_price(alert['price'])}\n\n"
                    f"Current Price: ${format_price(price)}\n"
                    f"Market Cap: ${token['mc']:,}\n\n"
                    f"Chart: {token['chart']}"
                )

                await context.bot.send_message(
                    CHAT_ID,
                    msg,
                    disable_web_page_preview=True
                )

        # PUMP ALERT
        if alert["type"] == "pump":
            timeframe = alert["tf"]
            threshold = alert["percent"]

            change = token[f"change{timeframe}"]

            if change >= threshold and not alert["triggered"]:
                alert["triggered"] = True

                msg = (
                    "🚀🚀 PUMP ALERT 🚀🚀\n\n"
                    f"{token['name']} ({token['symbol']}) is UP {change:.2f}% in {timeframe}\n\n"
                    f"Current Price: ${format_price(token['price'])}\n"
                    f"Market Cap: ${token['mc']:,}\n\n"
                    f"Chart: {token['chart']}"
                )

                await context.bot.send_message(
                    CHAT_ID,
                    msg,
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

        alert_id = str(uuid.uuid4())[:8]

        alerts[alert_id] = {
            "type": "price",
            "address": address,
            "price": price,
            "triggered": False,
        }

        await update.message.reply_text(
            f"✅ Price alert added for {token['symbol']}"
        )

    except:
        await update.message.reply_text("Usage: /add <token_address> <price>")


async def pump(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        address = context.args[0]
        percent = float(context.args[1])
        tf = context.args[2]

        if tf not in ["5m", "1h", "6h"]:
            raise Exception

        token = get_token_data(address)
        if not token:
            await update.message.reply_text("❌ Token not found")
            return

        alert_id = str(uuid.uuid4())[:8]

        alerts[alert_id] = {
            "type": "pump",
            "address": address,
            "percent": percent,
            "tf": tf,
            "triggered": False,
        }

        await update.message.reply_text(
            f"🚀 Pump alert set for {token['symbol']} {percent}% in {tf}"
        )

    except:
        await update.message.reply_text(
            "Usage: /pump <address> <percent> <5m|1h|6h>"
        )


# ---------- LIST ALERTS ----------
async def list_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not alerts:
        await update.message.reply_text("No active alerts")
        return

    for alert_id, alert in alerts.items():
        token = get_token_data(alert["address"])
        if not token:
            continue

        if alert["type"] == "price":
            text = (
                f"📊 {token['name']} ({token['symbol']})\n"
                f"Alert: ${format_price(alert['price'])}"
            )
        else:
            text = (
                f"🚀 {token['name']} ({token['symbol']})\n"
                f"Pump Alert: {alert['percent']}% in {alert['tf']}"
            )

        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("❌ Remove Alert", callback_data=f"del_{alert_id}")]]
        )

        await update.message.reply_text(text, reply_markup=keyboard)


# ---------- DELETE ALERT ----------
async def delete_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    alert_id = query.data.replace("del_", "")

    if alert_id in alerts:
        del alerts[alert_id]
        await query.edit_message_text("✅ Alert removed")


# ---------- MAIN ----------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("pump", pump))
    app.add_handler(CommandHandler("list", list_alerts))
    app.add_handler(CallbackQueryHandler(delete_alert, pattern="^del_"))

    app.job_queue.run_repeating(monitor, interval=8, first=5)

    app.run_polling()


if __name__ == "__main__":
    main()
