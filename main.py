import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp

# --- إعدادات الآدمن ---
ADMIN_ID = 281448266  # ⚠️ ضع المعرف الخاص بك هنا (من @userinfobot)

def save_user(user_id):
    if not os.path.exists("users.txt"):
        with open("users.txt", "w") as f: f.write("")
    with open("users.txt", "r") as f:
        users = f.read().splitlines()
    if str(user_id) not in users:
        with open("users.txt", "a") as f: f.write(f"{user_id}\n")

# --- دالة البث الجماعي (Admin Only) ---
async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return # يتجاهل الأمر إذا لم تكن أنت الآدمن
    
    if not context.args:
        await update.message.reply_text("الرجاء كتابة الرسالة بعد الأمر.\nمثال: /broadcast السلام عليكم، تم تحديث البوت!")
        return
        
    message = " ".join(context.args)
    
    if not os.path.exists("users.txt"):
        await update.message.reply_text("لا يوجد مستخدمون حالياً.")
        return
        
    with open("users.txt", "r") as f:
        users = f.read().splitlines()
        
    success_count = 0
    await update.message.reply_text(f"⏳ جاري الإرسال لـ {len(users)} مستخدم...")
    
    for user_id in users:
        try:
            await context.bot.send_message(chat_id=user_id, text=message)
            success_count += 1
            await asyncio.sleep(0.1) # تأخير بسيط لتجنب الحظر من تليجرام
        except Exception:
            continue # تجاهل المستخدم الذي حظر البوت
            
    await update.message.reply_text(f"✅ تم الإرسال بنجاح لـ {success_count} مستخدم.")

# --- باقي الدوال (Start, Stats, Download) ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_user(update.effective_user.id)
    welcome_text = "مرحباً بك في بوت الجبوري للتحميل 🚀\nأرسل رابط أي فيديو وسأقوم بتحميله فوراً!"
    keyboard = [[InlineKeyboardButton("📸 إنستغرام", url="https://instagram.com/n35w"), InlineKeyboardButton("📢 قناتي", url="https://t.me/saad106")]]
    await update.message.reply_text(welcome_text, reply_markup=InlineKeyboardMarkup(keyboard))

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    count = 0
    if os.path.exists("users.txt"):
        with open("users.txt", "r") as f: count = len(f.read().splitlines())
    await update.message.reply_text(f"📊 عدد المشتركين: {count}")

async def download_and_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    if not url.startswith("http"): return
    status_msg = await update.message.reply_text("⏳ جاري التحميل...")
    file_path = f"video_{update.message.message_id}.mp4"
    ydl_opts = {'format': 'best', 'outtmpl': file_path, 'quiet': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl: ydl.download([url])
        with open(file_path, 'rb') as v: await update.message.reply_video(video=v, caption="تم التحميل بنجاح! ✅")
        await status_msg.delete()
    except: await status_msg.edit_text("❌ حدث خطأ، تأكد من الرابط.")
    finally:
        if os.path.exists(file_path): os.remove(file_path)

def main():
    BOT_TOKEN = "8932218353:AAEOFkZxVbrUt69lZxz1FmT3_Du1RiXoIB8"
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command)) # الأمر الجديد
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_and_send))
    application.run_polling()

if __name__ == '__main__':
    main()
