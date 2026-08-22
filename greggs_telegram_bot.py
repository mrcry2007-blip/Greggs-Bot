import os, sys, time, random, asyncio, logging, subprocess
from datetime import datetime
from pathlib import Path

try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "python-telegram-bot"])
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "selenium", "webdriver-manager"])
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager

BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
if not BOT_TOKEN:
    env_file = Path(".env")
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                if line.startswith("TELEGRAM_TOKEN="):
                    BOT_TOKEN = line.strip().split("=", 1)[1]
                    break
if not BOT_TOKEN:
    print("ERROR: TELEGRAM_TOKEN not set!")
    sys.exit(1)

FIRST_NAMES = ["James","Mary","John","Patricia","Robert","Jennifer"]
LAST_NAMES = ["Smith","Johnson","Williams","Brown","Jones","Garcia"]
PRODUCTS = ["Sausage Roll","Steak Bake","Chicken Bake"]
COMPLAINTS = [
    "I bought a {product} yesterday and was disappointed. Pastry was dry. Id appreciate compensation.",
    "The {product} I purchased today was stale and tasted off. Please look into this.",
    "Had a {product} that was barely edible. Cold and soggy. Very disappointing."
]

logging.basicConfig(format='%(asctime)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

def parse_emails(text):
    emails = []
    for sep in [',', ';', '\n']:
        if sep in text:
            for part in text.split(sep):
                part = part.strip()
                if part and '@' in part and '.' in part:
                    emails.append(part)
            break
    else:
        if text.strip() and '@' in text and '.' in text:
            emails = [text.strip()]
    valid = []
    seen = set()
    for e in emails:
        e = e.strip().lower()
        if e and '@' in e and '.' in e and e not in seen:
            valid.append(e)
            seen.add(e)
    return valid

def create_driver():
    try:
        options = Options()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--disable-blink-features=AutomationControlled')
        
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        return driver
    except Exception as e:
        logger.error(f"Driver error: {e}")
        return None

def submit_complaint(email, first_name, last_name):
    driver = None
    try:
        logger.info(f"Processing: {email}")
        driver = create_driver()
        if not driver:
            return False, "Browser failed"
        driver.get("https://www.greggs.com/contact")
        time.sleep(3)
        inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='text'], input[type='email']")
        if len(inputs) >= 3:
            inputs[0].send_keys(first_name)
            time.sleep(0.3)
            inputs[1].send_keys(last_name)
            time.sleep(0.3)
            inputs[2].send_keys(email)
            time.sleep(0.3)
        textareas = driver.find_elements(By.CSS_SELECTOR, "textarea")
        if textareas:
            textareas[0].send_keys(random.choice(COMPLAINTS).format(product=random.choice(PRODUCTS)))
            time.sleep(1)
        for cb in driver.find_elements(By.CSS_SELECTOR, "input[type='checkbox']"):
            if not cb.is_selected():
                driver.execute_script("arguments[0].click();", cb)
        for btn in driver.find_elements(By.CSS_SELECTOR, "button[type='submit'], form button"):
            if btn.is_displayed():
                driver.execute_script("arguments[0].click();", btn)
                break
        time.sleep(5)
        page = driver.page_source.lower()
        if any(w in page for w in ["thank", "success", "received", "submitted"]):
            return True, "Success"
        return False, "Unknown"
    except Exception as e:
        logger.error(f"Error: {e}")
        return False, str(e)[:50]
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass

class GreggsBot:
    def __init__(self):
        self.is_processing = False
        self.total = 0
        self.done = 0

    async def start(self, update, context):
        await update.message.reply_text("🤖 Greggs Bot\n\nSend emails separated by commas:\na@b.com, c@d.com\n\n/status - Check status\n/cancel - Stop\n/logs - View logs")

    async def status(self, update, context):
        await update.message.reply_text(f"Processing: {'Yes' if self.is_processing else 'No'}\nDone: {self.done}/{self.total}")

    async def cancel(self, update, context):
        if self.is_processing:
            self.is_processing = False
            await update.message.reply_text("Cancelled")
        else:
            await update.message.reply_text("Not processing")

    async def logs(self, update, context):
        try:
            if Path("bot.log").exists():
                with open("bot.log") as f:
                    await update.message.reply_text("Logs:\n" + "".join(f.readlines()[-15:]))
            else:
                await update.message.reply_text("No logs")
        except:
            await update.message.reply_text("Error reading logs")

    async def handle_emails(self, update, context):
        if self.is_processing:
            await update.message.reply_text("Busy! Use /cancel")
            return
        emails = parse_emails(update.message.text)
        if not emails:
            await update.message.reply_text("No valid emails found")
            return
        if len(emails) > 10:
            await update.message.reply_text(f"Max 10 emails, you sent {len(emails)}")
            return
        keyboard = [[InlineKeyboardButton("Start", callback_data="confirm")], [InlineKeyboardButton("Cancel", callback_data="cancel")]]
        context.user_data['emails'] = emails
        await update.message.reply_text(f"{len(emails)} emails ready. Start?", reply_markup=InlineKeyboardMarkup(keyboard))

    async def button_callback(self, update, context):
        query = update.callback_query
        await query.answer()
        if query.data == "cancel":
            await query.edit_message_text("Cancelled")
            return
        if query.data == "confirm":
            emails = context.user_data.get('emails', [])
            if not emails:
                await query.edit_message_text("No emails")
                return
            await query.edit_message_text(f"Processing {len(emails)} emails...")
            asyncio.create_task(self.process(update, context, emails))

    async def process(self, update, context, emails):
        self.is_processing = True
        self.total = len(emails)
        self.done = 0
        results = []
        success = 0
        try:
            for i, email in enumerate(emails, 1):
                if not self.is_processing:
                    break
                fn = random.choice(FIRST_NAMES)
                ln = random.choice(LAST_NAMES)
                await update.message.reply_text(f"[{i}/{len(emails)}] {email} - {fn} {ln}")
                ok, msg = submit_complaint(email, fn, ln)
                if ok:
                    success += 1
                    results.append(f"✅ {email}")
                else:
                    results.append(f"❌ {email}")
                self.done = i
                if i < len(emails):
                    await asyncio.sleep(8)
            await update.message.reply_text(f"Done! Success: {success}/{len(emails)}\n" + "\n".join(results[:10]))
        except Exception as e:
            await update.message.reply_text(f"Error: {e}")
        finally:
            self.is_processing = False

def main():
    print("="*50)
    print("  GREGGS BOT")
    print("="*50)
    bot = GreggsBot()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", bot.start))
    app.add_handler(CommandHandler("status", bot.status))
    app.add_handler(CommandHandler("cancel", bot.cancel))
    app.add_handler(CommandHandler("logs", bot.logs))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_emails))
    app.add_handler(CallbackQueryHandler(bot.button_callback))
    print("Bot running! Send /start on Telegram")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
