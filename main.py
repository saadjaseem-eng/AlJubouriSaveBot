import os
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import yt_dlp

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
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_and_send))
    
    print("البوت يعمل بنجاح...")
    application.run_polling()

if __name__ == '__main__':
    main()
