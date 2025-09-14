
# telegram_bot.py
# telegram_bot.py
import asyncio
from telegram import Bot

BOT_TOKEN = "8174967891:AAFiEBe8L6kP9sBqhW-Nu6Z_TeXYY2_E6XQ"

# create Bot once
bot = Bot(token=BOT_TOKEN)

def send_message(chat_id, text):
    """
    Sync wrapper that runs the async send_message coroutine.
    """
    try:
        # run the coroutine to actually send the message
        asyncio.run(bot.send_message(chat_id=chat_id, text=text))
        print(f"[Telegram] Sent message to {chat_id}")
    except Exception as e:
        print(f"[Telegram] Failed to send message to {chat_id}: {e}")

