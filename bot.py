import asyncio
import json
import os
from aiohttp import web
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters, ConversationHandler
from playwright.async_api import async_playwright

# আপনার টেলিগ্রাম বট টোকেন এখানে দিন
TELEGRAM_BOT_TOKEN = "8921379809:AAHVBrul_y7E28ucxEoKh1Fwbh3A1io9Nto"

# আপনার টেস্টিং ওয়েবসাইটের লগইন ইউআরএল এখানে দিন
TARGET_URL = "https://m.facebook.com/"

# কনভার্সেশন স্টেট
EMAIL, PASSWORD, PROXY = range(3)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 অটোমেশন টেস্ট বট সচল রয়েছে।\n\n"
        "দয়া করে আপনার অ্যাকাউন্টের **Username অথবা Email** দিন:"
    )
    return EMAIL

async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['email'] = update.message.text
    await update.message.reply_text("ধন্যবাদ! এখন আপনার অ্যাকাউন্টের **Password** দিন:")
    return PASSWORD

async def get_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['password'] = update.message.text
    await update.message.reply_text(
        "পাসওয়ার্ড রিসিভ করা হয়েছে।\n\n"
        "এবার প্রক্সি দিতে চাইলে ফরম্যাট অনুযায়ী দিন (যেমন: `ip:port:username:password`), "
        "অথবা প্রক্সি না থাকলে সরাসরি **skip** লিখুন:"
    )
    return PROXY

async def get_proxy_and_run(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    proxy_config = None
    
    if text.lower() != 'skip':
        parts = text.split(':')
        if len(parts) >= 2:
            ip, port = parts[0], parts[1]
            proxy_config = {"server": f"http://{ip}:{port}"}
            if len(parts) >= 4:
                proxy_config["username"] = parts[2]
                proxy_config["password"] = parts[3]

    email = context.user_data.get('email')
    password = context.user_data.get('password')

    await update.message.reply_text("🔄 ব্রাউজার অটোমেশন ও লগইন প্রসেস শুরু হচ্ছে, অনুগ্রহ করে অপেক্ষা করুন...")

    try:
        cookies_result = await run_playwright_login(TARGET_URL, email, password, proxy_config)
        
        if cookies_result["success"]:
            cookies_json = json.dumps(cookies_result["cookies"], indent=2)
            await update.message.reply_text("✅ লগইন সফল হয়েছে! নিচে কুকিজ ফাইল দেওয়া হলো:")
            
            file_path = "cookies.json"
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(cookies_json)
            
            with open(file_path, "rb") as doc:
                await update.message.reply_document(document=doc, caption="🔐 আপনার সেশন কুকিজ (Cookies)")
            
            if os.path.exists(file_path):
                os.remove(file_path)
        else:
            await update.message.reply_text(f"❌ লগইন ফেইল করেছে। কারণ: {cookies_result['error']}")
            
    except Exception as e:
        await update.message.reply_text(f"⚠️ টেকনিক্যাল এরর দেখা দিয়েছে: {str(e)}")

    return ConversationHandler.END

async def run_playwright_login(url, email, password, proxy):
    async with async_playwright() as p:
        browser_args = {"headless": True}
        if proxy:
            browser_args["proxy"] = proxy

        browser = await p.chromium.launch(**browser_args)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            await page.goto(url, timeout=60000)
            await page.fill('input[name*="email"], input[name*="user"], input[type="text"], input[type="email"]', email)
            await page.fill('input[name*="pass"], input[type="password"]', password)
            await page.click('button:has-text("Log in"), button[type="submit"], input[type="submit"]')
            await page.wait_for_timeout(5000)

            try:
                not_now_btn = page.locator('text=Not Now, text=Never, text=Cancel')
                if await not_now_btn.is_visible(timeout=3000):
                    await not_now_btn.click()
            except:
                pass

            cookies = await context.cookies()
            if cookies:
                await browser.close()
                return {"success": True, "cookies": cookies}
            else:
                await browser.close()
                return {"success": False, "error": "কুকিজ পাওয়া যায়নি, সম্ভবত লগইন ফেইল করেছে।"}

        except Exception as e:
            await browser.close()
            return {"success": False, "error": str(e)}

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("অপারেশন বাতিল করা হয়েছে। নতুন করে শুরু করতে `/start` লিখুন।")
    return ConversationHandler.END

# রেন্ডার ওয়েব সার্ভিসের জন্য ডামি সার্ভার
async def handle(request):
    return web.Response(text="Bot is running!")

async def web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            EMAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_email)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_password)],
            PROXY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_proxy_and_run)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    
    loop = asyncio.get_event_loop()
    loop.create_task(web_server())
    print("🤖 টেলিগ্রাম বট রান হচ্ছে...")
    app.run_polling()

if __name__ == "__main__":
    main()
