import os
import asyncio
import logging
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.error import TelegramError

# ==================================================
# الإعدادات
# ==================================================

ADMIN_ID = 281448266
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

# الحد التقريبي لحجم الملف المرسل إلى تيليجرام
MAX_FILE_SIZE = 49 * 1024 * 1024

BASE_DIR = Path(__file__).resolve().parent
USERS_FILE = BASE_DIR / "users.txt"

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("AlJubouriSaveBot")


# ==================================================
# إدارة المستخدمين
# ==================================================

def save_user(user_id: int) -> None:
    """حفظ معرف المستخدم مرة واحدة."""
    try:
        USERS_FILE.touch(exist_ok=True)

        with USERS_FILE.open("r", encoding="utf-8") as file:
            users = {line.strip() for line in file if line.strip()}

        user_id_text = str(user_id)

        if user_id_text not in users:
            with USERS_FILE.open("a", encoding="utf-8") as file:
                file.write(f"{user_id_text}\n")

    except OSError:
        logger.exception("تعذر حفظ المستخدم في users.txt")


def get_users() -> list[str]:
    """قراءة قائمة المستخدمين."""
    try:
        USERS_FILE.touch(exist_ok=True)

        with USERS_FILE.open("r", encoding="utf-8") as file:
            return list({
                line.strip()
                for line in file
                if line.strip().isdigit()
            })

    except OSError:
        logger.exception("تعذرت قراءة users.txt")
        return []


# ==================================================
# الأوامر الأساسية
# ==================================================

async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    message = update.effective_message
    user = update.effective_user

    if message is None or user is None:
        return

    save_user(user.id)

    welcome_text = (
        "مرحباً بك في بوت الجبوري للتحميل 🚀\n\n"
        "أرسل رابط فيديو من إحدى المنصات المدعومة "
        "وسأحاول تحميله وإرساله إليك.\n\n"
        "ملاحظة: بعض الروابط قد تتطلب تسجيل الدخول "
        "أو قد تكون غير متاحة للتحميل."
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "📸 إنستغرام",
                url="https://instagram.com/n35w",
            ),
            InlineKeyboardButton(
                "📢 قناتي",
                url="https://t.me/saad106",
            ),
        ]
    ]

    await message.reply_text(
        welcome_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def stats_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    message = update.effective_message
    user = update.effective_user

    if message is None or user is None:
        return

    if user.id != ADMIN_ID:
        return

    users = get_users()

    await message.reply_text(
        f"📊 عدد المستخدمين المسجلين: {len(users)}"
    )


async def broadcast_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    message = update.effective_message
    user = update.effective_user

    if message is None or user is None:
        return

    if user.id != ADMIN_ID:
        return

    if not context.args:
        await message.reply_text(
            "اكتب الرسالة بعد الأمر.\n"
            "مثال:\n"
            "/broadcast تم تحديث البوت 🚀"
        )
        return

    users = get_users()

    if not users:
        await message.reply_text("لا يوجد مستخدمون مسجلون.")
        return

    broadcast_text = " ".join(context.args)
    status = await message.reply_text(
        f"⏳ جاري إرسال الرسالة إلى {len(users)} مستخدم..."
    )

    success_count = 0
    failed_count = 0

    for user_id in users:
        try:
            await context.bot.send_message(
                chat_id=int(user_id),
                text=broadcast_text,
            )
            success_count += 1
            await asyncio.sleep(0.1)

        except TelegramError as error:
            failed_count += 1
            logger.warning(
                "فشل إرسال البث إلى المستخدم %s: %s",
                user_id,
                error,
            )

        except Exception:
            failed_count += 1
            logger.exception("خطأ غير متوقع أثناء البث")

    await status.edit_text(
        "✅ انتهى البث.\n"
        f"نجح الإرسال: {success_count}\n"
        f"تعذر الإرسال: {failed_count}"
    )


# ==================================================
# تنزيل الفيديو
# ==================================================

def is_valid_url(url: str) -> bool:
    """التأكد من أن النص رابط HTTP أو HTTPS."""
    try:
        parsed = urlparse(url.strip())
        return (
            parsed.scheme in ("http", "https")
            and bool(parsed.netloc)
        )
    except ValueError:
        return False


def download_video(url: str, output_dir: str) -> tuple[str, str]:
    """
    تنزيل الفيديو داخل مجلد مؤقت.
    تُنفّذ هذه الدالة خارج حلقة أحداث تيليجرام.
    """

    options = {
        # محاولة اختيار صيغة فيديو متوافقة دون دمج مسارات متعددة
        "format": (
            "best[ext=mp4][filesize<49000000]/"
            "best[filesize<49000000]/"
            "best[ext=mp4]/best"
        ),
        "outtmpl": os.path.join(output_dir, "%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": False,
        "retries": 2,
        "fragment_retries": 2,
        "socket_timeout": 30,
        "cachedir": False,
        # تمكين تنزيل مكونات EJS من GitHub عند الحاجة
        "remote_components": ["ejs:github"],
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=True)

        if not info:
            raise RuntimeError("لم تُرجع أداة التحميل معلومات الفيديو.")

        title = info.get("title") or "فيديو"

        requested_downloads = info.get("requested_downloads") or []
        candidates = []

        for item in requested_downloads:
            filepath = item.get("filepath")
            if filepath and os.path.isfile(filepath):
                candidates.append(filepath)

        if not candidates:
            prepared_path = ydl.prepare_filename(info)
            if os.path.isfile(prepared_path):
                candidates.append(prepared_path)

        if not candidates:
            candidates = [
                str(path)
                for path in Path(output_dir).iterdir()
                if path.is_file()
                and not path.name.endswith((".part", ".ytdl"))
            ]

        if not candidates:
            raise FileNotFoundError(
                "اكتمل طلب التنزيل، لكن لم يُعثر على ملف الفيديو."
            )

        # اختيار أكبر ملف مرشح باعتباره ملف الوسائط
        file_path = max(candidates, key=os.path.getsize)

        return file_path, title


async def download_and_send(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    message = update.effective_message

    if message is None or not message.text:
        return

    url = message.text.strip()

    if not is_valid_url(url):
        return

    status = await message.reply_text(
        "⏳ جارٍ فحص الرابط ومحاولة تنزيل الفيديو..."
    )

    try:
        with tempfile.TemporaryDirectory(prefix="jubouri_") as temp_dir:
            # تشغيل yt-dlp في خيط منفصل حتى لا يتوقف البوت عن الاستجابة
            file_path, title = await asyncio.to_thread(
                download_video,
                url,
                temp_dir,
            )

            file_size = os.path.getsize(file_path)

            if file_size == 0:
                raise RuntimeError("الملف الذي تم تنزيله فارغ.")

            if file_size > MAX_FILE_SIZE:
                await status.edit_text(
                    "⚠️ تم تنزيل الفيديو، لكن حجمه أكبر من الحد "
                    "الذي يستطيع البوت إرساله حاليًا.\n"
                    "جرّب رابطًا آخر أو فيديو أقصر."
                )
                return

            await status.edit_text("📤 اكتمل التنزيل، جارٍ الإرسال...")

            with open(file_path, "rb") as media:
                await message.reply_video(
                    video=media,
                    caption=f"✅ {title[:800]}",
                    supports_streaming=True,
                    read_timeout=120,
                    write_timeout=120,
                    connect_timeout=30,
                    pool_timeout=30,
                )

            await status.delete()

    except Exception as error:
        # تسجيل التفاصيل في Logs دون كشفها للمستخدم
        logger.exception("فشل تحميل الرابط: %s", url)

        error_text = str(error).lower()

        if "sign in to confirm" in error_text or "not a bot" in error_text:
            user_message = (
                "⚠️ يوتيوب يطلب التحقق من الطلب.\n"
                "جرّب رابطًا عامًا آخر. تحديث المكتبات وحده "
                "لا يضمن حل هذا النوع من القيود."
            )

        elif "private" in error_text or "login" in error_text:
            user_message = (
                "🔒 هذا الفيديو خاص أو يتطلب تسجيل الدخول، "
                "ولم يتمكن البوت من الوصول إليه."
            )

        elif (
            "unsupported url" in error_text
            or "no suitable extractor" in error_text
        ):
            user_message = (
                "❌ لا يستطيع yt-dlp التعرف على هذا الرابط حاليًا. "
                "قد تكون المنصة غير مدعومة أو غيّرت طريقة عرض الفيديو."
            )

        elif "too large" in error_text or "request entity too large" in error_text:
            user_message = (
                "⚠️ حجم الفيديو أكبر من الحد المسموح بإرساله."
            )

        else:
            user_message = (
                "❌ تعذر تحميل الفيديو.\n"
                "سجّل الخطأ في Logs، وجرّب رابطًا عامًا آخر."
            )

        try:
            await status.edit_text(user_message)
        except TelegramError:
            logger.exception("تعذر تحديث رسالة حالة التحميل")


# ==================================================
# معالجة الأخطاء العامة
# ==================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    logger.error(
        "حدث خطأ أثناء معالجة تحديث تيليجرام",
        exc_info=context.error,
    )


# ==================================================
# تشغيل البوت
# ==================================================

def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError(
            "متغير البيئة TELEGRAM_BOT_TOKEN غير موجود. "
            "أضف توكن البوت في إعدادات متغيرات البيئة في FadeHost."
        )

    application = Application.builder().token(BOT_TOKEN).build()

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

    logger.info("AlJubouriSaveBot is starting...")

    application.run_polling(
        drop_pending_updates=False,
        allowed_updates=Update.ALL_TYPES,
    )


if __name__ == "__main__":
    main()
