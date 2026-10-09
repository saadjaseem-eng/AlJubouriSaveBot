import os
import sys
import asyncio
import logging
import tempfile
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.error import TelegramError

# ==================================================
# SETTINGS
# ==================================================

ADMIN_ID = 281448266
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

BASE_DIR = Path(__file__).resolve().parent
USERS_FILE = BASE_DIR / "users.txt"

MAX_FILE_SIZE = 49 * 1024 * 1024
MAX_GALLERY_FILES = 8
DOWNLOAD_TIMEOUT = 240

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("AlJubouriSaveBot")


# ==================================================
# USERS
# ==================================================

def get_users():
    try:
        USERS_FILE.touch(exist_ok=True)
        with USERS_FILE.open("r", encoding="utf-8") as f:
            return sorted({
                line.strip()
                for line in f
                if line.strip().isdigit()
            })
    except OSError:
        logger.exception("Could not read users file")
        return []


def save_user(user_id):
    try:
        users = set(get_users())
        if str(user_id) not in users:
            with USERS_FILE.open("a", encoding="utf-8") as f:
                f.write(f"{user_id}\n")
    except OSError:
        logger.exception("Could not save user")


# ==================================================
# START / STATS / BROADCAST
# ==================================================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    user = update.effective_user

    if not message or not user:
        return

    save_user(user.id)

    keyboard = [[
        InlineKeyboardButton("📸 إنستغرام", url="https://instagram.com/n35w"),
        InlineKeyboardButton("📢 قناتي", url="https://t.me/saad106"),
    ]]

    await message.reply_text(
        "مرحباً بك في بوت الجبوري للتحميل 🚀\n\n"
        "أرسل رابط فيديو أو صورة من موقع مدعوم.\n"
        "سيحاول البوت استخراج الوسائط وإرسالها إليك.\n\n"
        "ملاحظة: بعض الروابط قد تتطلب تسجيل الدخول "
        "أو تكون محجوبة من الاستضافة.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.effective_message

    if not user or not message or user.id != ADMIN_ID:
        return

    await message.reply_text(
        f"📊 عدد المستخدمين المسجلين: {len(get_users())}"
    )


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    message = update.effective_message

    if not user or not message or user.id != ADMIN_ID:
        return

    if not context.args:
        await message.reply_text(
            "اكتب الرسالة بعد الأمر.\n"
            "مثال: /broadcast تم تحديث البوت 🚀"
        )
        return

    users = get_users()
    text = " ".join(context.args)

    status = await message.reply_text(
        f"⏳ جارٍ إرسال الرسالة إلى {len(users)} مستخدم..."
    )

    success = 0
    failed = 0

    for user_id in users:
        try:
            await context.bot.send_message(
                chat_id=int(user_id),
                text=text,
            )
            success += 1
            await asyncio.sleep(0.1)
        except TelegramError as exc:
            failed += 1
            logger.warning("Broadcast failed for %s: %s", user_id, exc)

    await status.edit_text(
        f"✅ انتهى البث.\nنجح: {success}\nتعذر: {failed}"
    )


# ==================================================
# URL VALIDATION
# ==================================================

def valid_url(url):
    try:
        parsed = urlparse(url.strip())
        return (
            parsed.scheme in ("http", "https")
            and bool(parsed.hostname)
        )
    except ValueError:
        return False


# ==================================================
# ENGINE 1: YT-DLP
# ==================================================

def download_with_ytdlp(url, folder):
    options = {
        "format": "best[ext=mp4]/best",
        "outtmpl": str(Path(folder) / "%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": False,
        "retries": 2,
        "fragment_retries": 2,
        "socket_timeout": 30,
        "cachedir": False,
        # تنزيل سكربتات EJS عند دعم الاتصال بـ GitHub
        "remote_components": ["ejs:github"],
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=True)

        if not info:
            raise RuntimeError("yt-dlp returned no video information")

        title = info.get("title") or "Media"
        candidates = []

        for item in info.get("requested_downloads") or []:
            filepath = item.get("filepath")
            if filepath and os.path.isfile(filepath):
                candidates.append(filepath)

        if not candidates:
            prepared = ydl.prepare_filename(info)
            if os.path.isfile(prepared):
                candidates.append(prepared)

        if not candidates:
            candidates = [
                str(p) for p in Path(folder).iterdir()
                if p.is_file()
                and not p.name.endswith((".part", ".ytdl", ".tmp"))
            ]

        if not candidates:
            raise FileNotFoundError("No downloaded file was found")

        return max(candidates, key=os.path.getsize), title


# ==================================================
# ENGINE 2: GALLERY-DL
# للصور والمعارض والمواقع التي يدعمها
# ==================================================

def download_with_gallery_dl(url, folder):
    command = [
        sys.executable,
        "-m",
        "gallery_dl",
        "--destination",
        folder,
        url,
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=DOWNLOAD_TIMEOUT,
        check=False,
    )

    if result.returncode != 0:
        # سجّل مقتطفًا من الخطأ فقط؛ لا تسجّل التوكنات أو الأسرار
        logger.warning(
            "gallery-dl failed: %s",
            (result.stderr or result.stdout or "Unknown error")[-1500:],
        )

    files = [
        p for p in Path(folder).rglob("*")
        if p.is_file()
        and not p.name.endswith((".part", ".tmp", ".ytdl"))
    ]

    if not files:
        raise RuntimeError(
            "gallery-dl could not extract downloadable media"
        )

    return sorted(files, key=lambda p: p.stat().st_size, reverse=True)


# ==================================================
# SEND DOWNLOADED FILES
# ==================================================

async def send_files(message, paths, title=""):
    sent = 0

    for path in paths[:MAX_GALLERY_FILES]:
        size = path.stat().st_size

        if size <= 0 or size > MAX_FILE_SIZE:
            logger.warning("Skipping file due to size: %s", path.name)
            continue

        with path.open("rb") as media:
            await message.reply_document(
                document=media,
                caption=(title[:700] if title and sent == 0 else None),
                read_timeout=120,
                write_timeout=120,
                connect_timeout=30,
            )

        sent += 1

    return sent


# ==================================================
# DOWNLOAD HANDLER
# ==================================================

async def download_and_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message

    if not message or not message.text:
        return

    url = message.text.strip()

    if not valid_url(url):
        return

    status = await message.reply_text("⏳ أفحص الرابط وأحاول تنزيل الوسائط...")

    try:
        with tempfile.TemporaryDirectory(prefix="jubouri_") as temp_dir:
            # المحرك الأول: الفيديوهات والمواقع التي يدعمها yt-dlp
            try:
                file_path, title = await asyncio.wait_for(
                    asyncio.to_thread(download_with_ytdlp, url, temp_dir),
                    timeout=DOWNLOAD_TIMEOUT,
                )

                path = Path(file_path)

                if not path.exists():
                    raise FileNotFoundError("Downloaded file disappeared")

                if path.stat().st_size > MAX_FILE_SIZE:
                    await status.edit_text(
                        "⚠️ الملف أكبر من الحد الاحترازي للإرسال. "
                        "جرّب فيديو أقصر أو أقل حجمًا."
                    )
                    return

                await status.edit_text("📤 اكتمل التنزيل، جارٍ الإرسال...")
                sent = await send_files(message, [path], title)

            except Exception as primary_error:
                logger.warning(
                    "yt-dlp failed (%s): %s",
                    type(primary_error).__name__,
                    str(primary_error)[:1000],
                )

                # المحرك الثاني: الصور والمعارض المدعومة
                await status.edit_text(
                    "↪️ لم ينجح محرك الفيديو. أجرب محرك الصور والمعارض..."
                )

                try:
                    files = await asyncio.wait_for(
                        asyncio.to_thread(
                            download_with_gallery_dl,
                            url,
                            temp_dir,
                        ),
                        timeout=DOWNLOAD_TIMEOUT,
                    )

                    await status.edit_text("📤 وجدت ملفات، جارٍ إرسالها...")
                    sent = await send_files(message, files, "تم استخراج الوسائط ✅")

                except Exception as secondary_error:
                    logger.warning(
                        "gallery-dl failed (%s): %s",
                        type(secondary_error).__name__,
                        str(secondary_error)[:1000],
                    )

                    error_text = str(primary_error).lower()

                    if (
                        "sign in to confirm" in error_text
                        or "not a bot" in error_text
                    ):
                        explanation = (
                            "⚠️ المنصة تطلب التحقق من الطلب الآلي. "
                            "تحديث المكتبات وحده لا يضمن حل هذه القيود."
                        )
                    elif "unsupported url" in error_text:
                        explanation = (
                            "❌ الرابط غير مدعوم من محركات الاستخراج الحالية."
                        )
                    elif "private" in error_text or "login" in error_text:
                        explanation = (
                            "🔒 المحتوى خاص أو يتطلب تسجيل الدخول."
                        )
                    else:
                        explanation = (
                            "❌ تعذر استخراج الوسائط من هذا الرابط "
                            "بأي من المحركين المتاحين."
                        )

                    await status.edit_text(explanation)
                    return

            if sent == 0:
                await status.edit_text(
                    "⚠️ لم يتم العثور على ملفات مناسبة للإرسال "
                    "أو أن الملفات تجاوزت الحد المسموح."
                )
            else:
                await status.delete()

    except asyncio.TimeoutError:
        await status.edit_text(
            "⏱️ استغرق التنزيل وقتًا أطول من المسموح. "
            "جرّب رابطًا أقصر أو أعد المحاولة لاحقًا."
        )
    except Exception:
        logger.exception("Unexpected error in download handler")
        try:
            await status.edit_text(
                "❌ حدث خطأ غير متوقع. راجع Logs لمعرفة السبب."
            )
        except TelegramError:
            pass


# ==================================================
# TELEGRAM ERRORS
# ==================================================

async def error_handler(update, context: ContextTypes.DEFAULT_TYPE):
    error = context.error

    logger.error(
        "Telegram update failed: %s",
        type(error).__name__ if error else "Unknown",
    )

    if error:
        logger.error("%s", str(error)[:1500])


# ==================================================
# STARTUP
# ==================================================

async def post_init(application: Application):
    # إزالة Webhook القديم حتى يتمكن Polling من العمل
    await application.bot.delete_webhook(drop_pending_updates=False)
    logger.info("Webhook cleared; polling will start.")


def main():
    if not BOT_TOKEN:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is missing from FadeHost environment variables"
        )

    logger.info("yt-dlp version: %s", yt_dlp.version.__version__)

    application = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            download_and_send,
        )
    )

    application.add_error_handler(error_handler)

    logger.info("AlJubouriSaveBot starting...")
    application.run_polling(
        drop_pending_updates=False,
        allowed_updates=Update.ALL_TYPES,
    )


if __name__ == "__main__":
    main()
