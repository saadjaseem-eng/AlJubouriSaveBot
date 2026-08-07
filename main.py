import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp

# --- دالة الترحيب عند الضغط على /start ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "مرحباً بك في **بوت الجبوري للتحميل** 🚀\n\n"
        "أسرع بوت مجاني وخالي من الإعلانات لتحميل الفيديوهات والوسائط بأعلى جودة!\n\n"
        "📌 **المنصات المدعومة:**\n"
        "• تيك توك (TikTok) - بدون علامة مائية\n"
        "• إنستغرام (Reels & Posts)\n"
        "• يوتيوب (YouTube Videos & Shorts)\n"
        "• فيسبوك (Facebook)\n"
        "• منصة X (تويتر)\n\n"
        "📥 **كيفية الاستخدام:**\n"
        "فقط قم بإرسال رابط الفيديو هنا وسأقوم بتحميله لك فوراً!\n\n"
        "👇 **للتواصل والمتابعة عبر حساباتنا:**"
    )
    
    # إضافة أزرار شفافة أسفل الرسالة الترحيبية للرابط المباشر
    keyboard = [
        [
            InlineKeyboardButton("📸 حساب الإنستغرام", url="https://instagram.com/n35w"),
            InlineKeyboardButton("📢 قناة التليجرام", url="https://t.me/saad_130")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        text=welcome_text, 
        parse_mode="Markdown", 
        reply_markup=reply_markup,
        disable_web_page_preview=True
    )

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
    # ⚠️ استبدل النص أسفله بالـ Token الخاص بك من BotFather
    BOT_TOKEN = "8932218353:AAEOFkZxVbrUt69lZxz1FmT3_Du1RiXoIB8"
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    # إضافة معالج أمر start والرسائل
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_and_send))
    
    print("البوت يعمل بنجاح...")
    application.run_polling()

if __name__ == '__main__':
    main()
