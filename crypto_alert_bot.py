import asyncio
import json
import aiohttp
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters

# ------------------------
# CONFIGURATION
# ------------------------
BOT_TOKEN = "8469965625:AAFSvsOKpijGV7A78yrtvQ4Hr7Dby3ulRzs"
ALERTS_FILE = "alerts.json"
POLL_INTERVAL = 10  # seconds

# ------------------------
# GLOBAL VARIABLES
# ------------------------
alerts = {}  # {chat_id: [alert_dicts]}

# ------------------------
# HELPER FUNCTIONS
# ------------------------
def load_alerts():
    global alerts
    try:
        with open(ALERTS_FILE, "r") as f:
            alerts = json.load(f)
    except:
        alerts = {}

def save_alerts():
    try:
        with open(ALERTS_FILE, "w") as f:
            json.dump(alerts, f, indent=2)
    except Exception as e:
        print("Error saving alerts:", e)

def format_price(price):
    # Prevent scientific notation
    if price < 0.0001:
        return f"{price:.8f}"
    else:
        return f"{price:.6f}"

async def fetch_token_data(contract):
    url = f"https://api.dexscreener.com/latest/dex/tokens/{contract}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    print(f"Error fetching {contract}: status {resp.status}")
                    return None
    except Exception as e:
        print(f"Exception fetching {contract}: {e}")
        return None

# ------------------------
# COMMAND HANDLERS
# ------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome! Use /add to create alerts, /list to see them.")

async def add_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        args = context.args
        if len(args) < 3:
            await update.message.reply_text("Usage: /add <contract> <value> <price|percent>")
            return

        contract = args[0]
        value = float(args[1])
        alert_type = args[2].lower()
        chat_id = str(update.effective_chat.id)

        token_data = await fetch_token_data(contract)
        if not token_data or not token_data.get("pairs"):
            await update.message.reply_text("Could not fetch token data or no pairs available.")
            return

        token_name = token_data["pairs"][0]["baseToken"].get("name", "Unknown")
        symbol = token_data["pairs"][0]["baseToken"].get("symbol", "UNK")

        alert = {
            "contract": contract,
            "value": value,
            "type": alert_type,
            "token_name": token_name,
            "symbol": symbol
        }

        if chat_id not in alerts:
            alerts[chat_id] = []
        alerts[chat_id].append(alert)
        save_alerts()
        await update.message.reply_text(f"✅ Alert added for {token_name} ({symbol})")
    except Exception as e:
        await update.message.reply_text(f"Error adding alert: {e}")

# ------------------------
# LIST WITH INLINE BUTTONS
# ------------------------
async def list_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)

    if chat_id not in alerts or not alerts[chat_id]:
        await update.message.reply_text("No active alerts.")
        return

    for i, alert in enumerate(alerts[chat_id], start=1):
        token = alert.get("token_name", "Unknown")
        symbol = alert.get("symbol", "UNK")
        value = alert.get("value", 0)
        alert_type = alert.get("type", "price")

        if alert_type == "price":
            text = f"{i}. {token} ({symbol})\nPrice Alert: ${format_price(value)}"
        else:
            text = f"{i}. {token} ({symbol})\n% Change Alert: {value}%"

        keyboard = [
            [
                InlineKeyboardButton("✏️ Edit Price", callback_data=f"edit_price_{i-1}"),
                InlineKeyboardButton("📈 Edit %", callback_data=f"edit_percent_{i-1}")
            ],
            [
                InlineKeyboardButton("🗑 Delete", callback_data=f"delete_{i-1}")
            ]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(text, reply_markup=reply_markup)

# ------------------------
# BUTTON CALLBACK HANDLER
# ------------------------
async def handle_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    chat_id = str(query.message.chat.id)
    data = query.data

    if chat_id not in alerts:
        await query.edit_message_text("No alerts found.")
        return

    try:
        parts = data.split("_")
        action = parts[0]
        index = int(parts[-1])
    except:
        await query.edit_message_text("Invalid callback data.")
        return

    if index >= len(alerts[chat_id]):
        await query.edit_message_text("Alert not found.")
        return

    alert = alerts[chat_id][index]

    try:
        if action == "delete":
            alerts[chat_id].pop(index)
            save_alerts()
            await query.edit_message_text("✅ Alert deleted.")
        elif action == "edit" and parts[1] == "price":
            context.user_data["edit_index"] = index
            context.user_data["edit_type"] = "price"
            await query.message.reply_text("Send the new trigger price:")
        elif action == "edit" and parts[1] == "percent":
            context.user_data["edit_index"] = index
            context.user_data["edit_type"] = "percent"
            await query.message.reply_text("Send the new % change trigger:")
    except Exception as e:
        print("Error in handle_buttons:", e)
        await query.edit_message_text("Error processing button click.")

# ------------------------
# HANDLE EDIT RESPONSES
# ------------------------
async def handle_edit_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "edit_index" not in context.user_data:
        return

    chat_id = str(update.effective_chat.id)
    index = context.user_data["edit_index"]
    edit_type = context.user_data["edit_type"]

    if chat_id not in alerts or index >= len(alerts[chat_id]):
        context.user_data.clear()
        return

    try:
        new_value = float(update.message.text)
    except:
        await update.message.reply_text("Invalid number.")
        return

    alerts[chat_id][index]["value"] = new_value
    save_alerts()
    context.user_data.clear()
    await update.message.reply_text("✅ Alert updated.")

# ------------------------
# PRICE POLLING TASK
# ------------------------
async def price_polling_task(app):
    while True:
        try:
            for chat_id, user_alerts in alerts.items():
                for alert in user_alerts.copy():
                    try:
                        token_data = await fetch_token_data(alert["contract"])
                        if not token_data or not token_data.get("pairs"):
                            continue

                        pair = token_data["pairs"][0]
                        current_price = float(pair.get("priceUsd", 0))
                        market_cap = float(pair.get("marketCap", 0))
                        token_name = pair["baseToken"].get("name", "Unknown")
                        symbol = pair["baseToken"].get("symbol", "UNK")

                        # Price Alert
                        if alert["type"] == "price" and current_price >= alert["value"]:
                            text = (
                                f"{token_name} ({symbol}) went above ${format_price(alert['value'])}\n"
                                f"Current Price: ${format_price(current_price)}\n"
                                f"Market Cap: ${market_cap:,.0f}"
                            )
                            await app.bot.send_message(chat_id=int(chat_id), text=text)
                            user_alerts.remove(alert)
                            save_alerts()

                        # Percent Change Alert
                        elif alert["type"] == "percent":
                            timeframe = alert.get("timeframe", "1h")
                            change_key = {
                                "5m": "priceChange5m",
                                "1h": "priceChange1h",
                                "6h": "priceChange6h",
                                "24h": "priceChange24h"
                            }.get(timeframe, "priceChange1h")
                            percent_change = float(pair.get(change_key, 0))
                            if percent_change >= alert["value"]:
                                text = (
                                    f"{token_name} ({symbol}) price increased by {percent_change:.2f}% over {timeframe}\n"
                                    f"Current Price: ${format_price(current_price)}\n"
                                    f"Market Cap: ${market_cap:,.0f}"
                                )
                                await app.bot.send_message(chat_id=int(chat_id), text=text)
                                user_alerts.remove(alert)
                                save_alerts()
                    except Exception as e:
                        print(f"Error processing alert for {alert.get('contract','unknown')}: {e}")
        except Exception as e:
            print("Error in polling task:", e)
        await asyncio.sleep(POLL_INTERVAL)

# ------------------------
# MAIN FUNCTION
# ------------------------
async def main():
    load_alerts()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add_alert))
    app.add_handler(CommandHandler("list", list_alerts))
    app.add_handler(CallbackQueryHandler(handle_buttons))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_edit_response))

    # Start polling task
    asyncio.create_task(price_polling_task(app))

    await app.run_polling()

# ------------------------
# RUN
# ------------------------
if __name__ == "__main__":
    asyncio.run(main())
