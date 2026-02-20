import os
import requests
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

BOT_TOKEN = os.getenv("BOT_TOKEN")

alerts = {}

DEX_API = "https://api.dexscreener.com/latest/dex/tokens/"

def format_price(p):
    if p < 0.000001:
        return f"{p:.10f}".rstrip("0")
    elif p < 1:
        return f"{p:.6f}".rstrip("0")
    else:
        return f"{p:.2f}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Alert bot ready.")

async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        token = context.args[0]
        price = float(context.args[1])
        alerts[token] = price
        await update.message.reply_text(f"Alert added for {token} at {price}")
    except:
        await update.message.reply_text("Usage: /add TOKEN_ADDRESS PRICE")

async def list_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not alerts:
        await update.message.reply_text("No active alerts.")
        return
    msg = "\n".join([f"{k} → {v}" for k, v in alerts.items()])
    await update.message.reply_text(msg)

async def monitor(context: ContextTypes.DEFAULT_TYPE):
    for token, target in list(alerts.items()):
        try:
            r = requests.get(DEX_API + token, timeout=10)
            data = r.json()["pairs"][0]

            price = float(data["priceUsd"])
            change = data["priceChange"]

            if price >= target:
                msg = (
                    f"🚨 PRICE ALERT\n\n"
                    f"Price: ${format_price(price)}\n"
                    f"Target: ${format_price(target)}\n\n"
                    f"5m: {change['m5']}%\n"
                    f"1h: {change['h1']}%\n"
                    f"6h: {change['h6']}%\n"
                    f"24h: {change['h24']}%"
                )

                await context.bot.send_message(
                    chat_id=context.job.chat_id,
                    text=msg
                )

                del alerts[token]

        except:
            pass

async def start_monitor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.job_queue.run_repeating(
        monitor,
        interval=8,   # FAST monitoring
        first=3,
        chat_id=update.effective_chat.id
    )
    await update.message.reply_text("Monitoring started.")

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("list", list_alerts))
    app.add_handler(CommandHandler("monitor", start_monitor))

    app.run_polling()

if __name__ == "__main__":
    main()
