import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp

# --- قائمة المعرفات المسموح لها برؤية الإحصائيات (ضع معرفك هنا) ---
ADMIN_ID = 281448266  # استبدل هذا المعرف بمعرف حسابك الشخصي في تليجرام

def save_user(user_id):
    """حفظ معرف المستخدم إذا لم يكن موجوداً من قبل"""
    if not os.path.exists("users.txt"):
        with open("users.txt", "w") as f:
            f.write("")
            
    with open("users.txt", "r") as f:
        users = f.read().splitlines()
        
    if str(user_id) not in users:
        with open("users.txt", "a") as f:
            f.write(f"{user_id}\n")

# --- دالة الترحيب مع حفظ المستخدم ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    save_user(user_id) # حفظ المستخدم جديد
    
    welcome_text = (
        "مرحباً بك في **بوت الجبوري للتحميل** 🚀\n\n"
        "أسرع بوت مجاني وخالي من الإعلانات لتحميل الفيديوهات والوسائط بأعلى جودة!\n\n"
        "📌 **المنصات المدعومة:**\n"
        "• تيك توك (TikTok)\n"
        "• إنستغرام (Reels & Posts)\n"
        "• يوتيوب (YouTube Videos & Shorts)\n"
        "• فيسبوك (Facebook)\n"
        "• منصة X (تويتر)\n\n"
        "📥 أرسل رابط الفيديو للبدء!"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("📸 حساب الإنستغرام", url="https://instagram.com/n35w"),
            InlineKeyboardButton("📢 قناة التليجرام", url="https://t.me/saad106")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        text=welcome_text, 
        parse_mode="Markdown", 
        reply_markup=reply_markup,
        disable_web_page_preview=True
    )

# --- دالة عرض الإحصائيات للآدمن فقط ---
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return # عدم الرد إذا لم يكن الآدمن
        
    count = 0
    if os.path.exists("users.txt"):
        with open("users.txt", "r") as f:
            count = len(f.read().splitlines())
            
    await update.message.reply_text(f"📊 **إحصائيات البوت:**\n\nعدد المستخدمين الإجمالي: **{count}** مشترك")

# --- دالة التحميل والإرسال ---
async def download_and_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    
    if not url.startswith("http://") and not url.startswith("https://"):
        return

    status_msg = await update.message.reply_text("⏳ جاري التحميل، يرجى الانتظار...")
    file_path = f"video_{update.message.message_id}.mp4"

    ydl_opts = {
        'format': 'best',
        'outtmpl': file_path,
        'quiet': True,
        'no_warnings': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'check_formats': False,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        with open(file_path, 'rb') as video_file:
            await update.message.reply_video(video=video_file, caption="تم التحميل بنجاح عبر بوت الجبوري! ✅")
            
        await status_msg.delete()

    except Exception as e:
        await status_msg.edit_text("❌ حدث خطأ أثناء التحميل. تأكد من صحة الرابط.")
    
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

def main():
    BOT_TOKEN = "8932218353:AAEOFkZxVbrUt69lZxz1FmT3_Du1RiXoIB8"
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("stats", stats_command)) # أمر الإحصائيات
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_and_send))
    
    print("البوت يعمل بنجاح...")
    application.run_polling()

if __name__ == '__main__':
    main()
