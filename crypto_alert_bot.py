import os
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
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
            "change5m": pair.get("priceChange", {}).get("m5", 0),
            "change1h": pair.get("priceChange", {}).get("h1", 0),
            "change6h": pair.get("priceChange", {}).get("h6", 0),
        }
    except:
        return None


# ---------- MONITOR LOOP ----------
async def monitor(context: ContextTypes.DEFAULT_TYPE):
    for addr, data in list(alerts.items()):
        token = get_token_data(addr)
        if not token:
            continue

        price = token["price"]

        # -------- PRICE TARGET ALERT --------
        if data["type"] == "price":
            if price >= data["price"] and not data["triggered"]:
                data["triggered"] = True

                keyboard = InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Remove Alert", callback_data=f"del_{addr}")]]
                )

                msg = (
                    "🚨🚨 DEX PRICE ALERT 🚨🚨\n\n"
                    f"{token['name']} ({token['symbol']}) went above ${format_price(data['price'])}\n\n"
                    f"Current Price: ${format_price(price)}\n"
                    f"Market Cap: ${token['mc']:,}\n\n"
                    f"Chart: {token['chart']}"
                )

                await context.bot.send_message(
                    chat_id=CHAT_ID,
                    text=msg,
                    reply_markup=keyboard,
                    disable_web_page_preview=True,
                )

        # -------- PERCENT ALERT --------
        elif data["type"] == "percent":
            change = token[f"change{data['time']}"]

            if change >= data["percent"] and not data["triggered"]:
                data["triggered"] = True

                keyboard = InlineKeyboardMarkup(
                    [[InlineKeyboardButton("❌ Remove Alert", callback_data=f"del_{addr}")]]
                )

                msg = (
                    "🚀🚀 PERCENT ALERT 🚀🚀\n\n"
                    f"{token['name']} ({token['symbol']})\n"
                    f"Up {change:.2f}% in {data['time']}\n\n"
                    f"Price: ${format_price(price)}\n"
                    f"Chart: {token['chart']}"
                )

                await context.bot.send_message(
                    chat_id=CHAT_ID,
                    text=msg,
                    reply_markup=keyboard,
                    disable_web_page_preview=True,
                )


# ---------- DELETE ALERT ----------
async def delete_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    addr = query.data.replace("del_", "")

    if addr in alerts:
        del alerts[addr]
        await query.edit_message_text("✅ Alert removed")
    else:
        await query.edit_message_text("Alert already removed")


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
            "type": "price",
            "price": price,
            "triggered": False,
        }

        await update.message.reply_text(
            f"✅ Price alert added for {token['name']} ({token['symbol']})"
        )
    except:
        await update.message.reply_text("Usage: /add <token_address> <price>")


# ---------- PERCENT COMMAND ----------
async def addpercent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        address = context.args[0]
        percent = float(context.args[1])
        timeframe = context.args[2]

        if timeframe not in ["5m", "1h", "6h"]:
            await update.message.reply_text("Use 5m, 1h, or 6h")
            return

        token = get_token_data(address)
        if not token:
            await update.message.reply_text("Token not found")
            return

        alerts[address] = {
            "type": "percent",
            "percent": percent,
            "time": timeframe,
            "triggered": False,
        }

        await update.message.reply_text(
            f"✅ Percent alert added for {token['symbol']} ({percent}% in {timeframe})"
        )
    except:
        await update.message.reply_text(
            "Usage: /addpercent <address> <percent> <5m|1h|6h>"
        )


async def list_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not alerts:
        await update.message.reply_text("No active alerts")
        return

    msg = "📊 Active Alerts:\n\n"

    for addr, data in alerts.items():
        token = get_token_data(addr)
        if not token:
            continue

        if data["type"] == "price":
            msg += f"{token['symbol']} → ${format_price(data['price'])}\n"
        else:
            msg += f"{token['symbol']} → {data['percent']}% in {data['time']}\n"

    await update.message.reply_text(msg)


# ---------- MAIN ----------
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("addpercent", addpercent))
    app.add_handler(CommandHandler("list", list_alerts))
    app.add_handler(CallbackQueryHandler(delete_alert))

    app.job_queue.run_repeating(monitor, interval=8, first=3)

    app.run_polling()


if __name__ == "__main__":
    main()
