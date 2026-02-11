import time
import sqlite3
import requests
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import os

# ------------------ CONFIG ------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = int(os.getenv("CHAT_ID"))
CHECK_INTERVAL = 60  # seconds

# ------------------ DATABASE ------------------
conn = sqlite3.connect("alerts.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER,
    contract TEXT,
    direction TEXT,      -- 'above', 'below', 'pump', 'dump'
    target REAL,         -- price or percent
    triggered INTEGER DEFAULT 0,
    start_time TEXT,     -- only for pump/dump
    reference_price REAL -- only for pump/dump
)
""")
conn.commit()

# ------------------ PRICE FETCH ------------------
def get_price(contract):
    url = f"https://api.dexscreener.com/latest/dex/tokens/{contract}"
    try:
        data = requests.get(url, timeout=10).json()
        if not data.get("pairs"):
            return None
        pair = max(
            data["pairs"],
            key=lambda p: float(p["liquidity"]["usd"] or 0)
        )
        return float(pair["priceUsd"])
    except:
        return None

# ------------------ COMMANDS ------------------
async def alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID:
        return
    try:
        contract, direction, target = context.args
        direction = direction.lower()
        target = float(target)
        if direction not in ["above", "below"]:
            raise ValueError
        cursor.execute(
            "INSERT INTO alerts (chat_id, contract, direction, target) VALUES (?, ?, ?, ?)",
            (CHAT_ID, contract, direction, target)
        )
        conn.commit()
        await update.message.reply_text(f"✅ Price alert set: {direction.upper()} ${target}")
    except:
        await update.message.reply_text("Usage:\n/alert <contract> above|below <price>")

async def pump(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID:
        return
    try:
        contract, percent, window = context.args
        percent = float(percent)
        # parse time window
        if window.endswith("h"):
            seconds = int(window[:-1]) * 3600
        elif window.endswith("m"):
            seconds = int(window[:-1]) * 60
        else:
            await update.message.reply_text("Time format: 1h, 30m, etc.")
            return

        price = get_price(contract)
        if price is None:
            await update.message.reply_text("Error fetching token price.")
            return

        cursor.execute(
            "INSERT INTO alerts (chat_id, contract, direction, target, start_time, reference_price) VALUES (?, ?, ?, ?, ?, ?)",
            (CHAT_ID, contract, "pump", percent, datetime.utcnow().isoformat(), price)
        )
        conn.commit()
        await update.message.reply_text(
            f"✅ Pump alert set: +{percent}% in {window}\nReference price: ${price}"
        )
    except:
        await update.message.reply_text("Usage:\n/pump <contract> <percent> <time_window>")

async def dump(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.id != CHAT_ID:
        return
    try:
        contract, percent, window = context.args
        percent = float(percent)
        if window.endswith("h"):
            seconds = int(window[:-1]) * 3600
        elif window.endswith("m"):
            seconds = int(window[:-1]) * 60
        else:
            await update.message.reply_text("Time format: 1h, 30m, etc.")
            return

        price = get_price(contract)
        if price is None:
            await update.message.reply_text("Error fetching token price.")
            return

        cursor.execute(
            "INSERT INTO alerts (chat_id, contract, direction, target, start_time, reference_price) VALUES (?, ?, ?, ?, ?, ?)",
            (CHAT_ID, contract, "dump", -percent, datetime.utcnow().isoformat(), price)
        )
        conn.commit()
        await update.message.reply_text(
            f"✅ Dump alert set: -{percent}% in {window}\nReference price: ${price}"
        )
    except:
        await update.message.reply_text("Usage:\n/dump <contract> <percent> <time_window>")

async def list_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT id, contract, direction, target FROM alerts WHERE triggered = 0")
    rows = cursor.fetchall()
    if not rows:
        await update.message.reply_text("No active alerts.")
        return
    msg = "📋 Active Alerts:\n"
    for r in rows:
        msg += f"{r[0]}. {r[1][:8]}... {r[2]} {r[3]}\n"
    await update.message.reply_text(msg)

async def remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        alert_id = int(context.args[0])
        cursor.execute("DELETE FROM alerts WHERE id = ?", (alert_id,))
        conn.commit()
        await update.message.reply_text("🗑 Alert removed.")
    except:
        await update.message.reply_text("Usage:\n/remove <alert_id>")

# ------------------ CHECK LOOP ------------------
async def price_checker(app):
    while True:
        cursor.execute("SELECT * FROM alerts WHERE triggered = 0")
        alerts = cursor.fetchall()

        for alert in alerts:
            alert_id, chat_id, contract, direction, target, triggered, start_time, reference_price = alert
            price = get_price(contract)
            if price is None:
                continue

            # ----------------- Price Alerts -----------------
            if direction in ["above", "below"]:
                if (direction == "above" and price >= target) or (direction == "below" and price <= target):
                    await app.bot.send_message(
                        chat_id=chat_id,
                        text=f"🚨 ALERT 🚨\nPrice hit ${price}\n{contract[:10]}..."
                    )
                    cursor.execute("UPDATE alerts SET triggered=1 WHERE id=?", (alert_id,))
                    conn.commit()

            # ----------------- % Move Alerts -----------------
            elif direction in ["pump", "dump"]:
                ref_price = reference_price
                start = datetime.fromisoformat(start_time)
                now = datetime.utcnow()
                if direction == "pump":
                    percent_change = ((price - ref_price) / ref_price) * 100
                    if percent_change >= target:
                        await app.bot.send_message(
                            chat_id=chat_id,
                            text=f"🚀 PUMP ALERT 🚀\n{contract[:10]}...\nPrice: ${price} (+{percent_change:.2f}%)"
                        )
                        cursor.execute("UPDATE alerts SET triggered=1 WHERE id=?", (alert_id,))
                        conn.commit()
                    elif now - start > timedelta(hours=24):  # expire after 24h if not triggered
                        cursor.execute("UPDATE alerts SET triggered=1 WHERE id=?", (alert_id,))
                        conn.commit()
                elif direction == "dump":
                    percent_change = ((price - ref_price) / ref_price) * 100
                    if percent_change <= target:  # target is negative
                        await app.bot.send_message(
                            chat_id=chat_id,
                            text=f"🛑 DUMP ALERT 🛑\n{contract[:10]}...\nPrice: ${price} ({percent_change:.2f}%)"
                        )
                        cursor.execute("UPDATE alerts SET triggered=1 WHERE id=?", (alert_id,))
                        conn.commit()
                    elif now - start > timedelta(hours=24):
                        cursor.execute("UPDATE alerts SET triggered=1 WHERE id=?", (alert_id,))
                        conn.commit()

        time.sleep(CHECK_INTERVAL)

# ------------------ MAIN ------------------
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("alert", alert))
    app.add_handler(CommandHandler("pump", pump))
    app.add_handler(CommandHandler("dump", dump))
    app.add_handler(CommandHandler("list", list_alerts))
    app.add_handler(CommandHandler("remove", remove))

    app.create_task(price_checker(app))
    await app.run_polling()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())