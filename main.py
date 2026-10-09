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
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from telegram.error import TelegramError, Conflict, NetworkError

# =====================================================
# إعدادات البوت
# =====================================================

ADMIN_ID = 281448266
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

BASE_DIR = Path(__file__).resolve().parent
USERS_FILE = BASE_DIR / "users.txt"

# حد احترازي لحجم الملف قبل إرساله عبر تيليجرام
MAX_FILE_SIZE = 49 * 1024 * 1024

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("AlJubouriSaveBot")


# =====================================================
# إدارة المستخدمين
# =====================================================

def get_users() -> list[str]:
    try:
        USERS_FILE.touch(exist_ok=True)

        with USERS_FILE.open("r", encoding="utf-8") as file:
            return sorted({
                line.strip()
                for line in file
                if line.strip().isdigit()
            })

    except OSError:
        logger.exception("تعذرت قراءة قائمة المستخدمين")
        return []


def save_user(user_id: int) -> None:
    try:
        user_id_text = str(user_id)
        users = set(get_users())

        if user_id_text not in users:
            with USERS_FILE.open("a", encoding="utf-8") as file:
                file.write(f"{user_id_text}\n")

    except OSError:
        logger.exception("تعذر حفظ المستخدم")


# =====================================================
# تهيئة استقبال تحديثات تيليجرام
# =====================================================

async def post_init(application: Application) -> None:
    """
    إزالة Webhook القديم قبل بدء Polling.
    لا تستخدم Webhook وPolling في الوقت نفسه.
    """
    try:
        await application.bot.delete_webhook(
            drop_pending_updates=False
        )
        logger.info("تم التحقق من Webhook وتجهيز Polling.")

    except Exception:
        logger.exception(
            "تعذر حذف Webhook. تحقق من التوكن واتصال تيليجرام."
        )
        raise


# =====================================================
# /start
# =====================================================

async def start_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    message = update.effective_message
    user = update.effective_user

    if message is None or user is None:
        return

    save_user(user.id)

    text = (
        "مرحباً بك في بوت الجبوري للتحميل 🚀\n\n"
        "أرسل رابط فيديو وسأحاول تحميله وإرساله إليك.\n\n"
        "يدعم البوت المواقع التي تستطيع أداة التحميل "
        "التعرف عليها والوصول إلى محتواها.\n\n"
        "ملاحظة: بعض الفيديوهات قد تكون خاصة أو تتطلب "
        "تسجيل الدخول أو تكون محجوبة من الاستضافة."
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
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


# =====================================================
# /stats
# =====================================================

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

    await message.reply_text(
        f"📊 عدد المستخدمين المسجلين: {len(get_users())}"
    )


# =====================================================
# /broadcast
# =====================================================

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
        f"⏳ جارٍ إرسال الرسالة إلى {len(users)} مستخدم..."
    )

    success = 0
    failed = 0

    for user_id in users:
        try:
            await context.bot.send_message(
                chat_id=int(user_id),
                text=broadcast_text,
            )
            success += 1
            await asyncio.sleep(0.1)

        except TelegramError as error:
            failed += 1
            logger.warning(
                "تعذر إرسال البث إلى %s: %s",
                user_id,
                error,
            )

    await status.edit_text(
        "✅ انتهى البث.\n"
        f"نجح الإرسال: {success}\n"
        f"تعذر الإرسال: {failed}"
    )


# =====================================================
# التحقق من الروابط
# =====================================================

def is_valid_url(url: str) -> bool:
    try:
        parsed = urlparse(url.strip())

        return (
            parsed.scheme in ("http", "https")
            and bool(parsed.netloc)
        )

    except ValueError:
        return False


# =====================================================
# تنزيل الوسائط باستخدام yt-dlp
# =====================================================

def download_media(url: str, directory: str) -> tuple[str, str]:
    """
    دالة متزامنة؛ سيتم تشغيلها داخل خيط منفصل
    كي لا يتوقف البوت عن الاستجابة أثناء التنزيل.
    """

    options = {
        "format": (
            "best[ext=mp4][filesize<49000000]/"
            "best[filesize<49000000]/"
            "best[ext=mp4]/best"
        ),
        "outtmpl": os.path.join(
            directory,
            "%(id)s.%(ext)s",
        ),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": False,
        "retries": 2,
        "fragment_retries": 2,
        "socket_timeout": 30,
        "cachedir": False,
    }

    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=True)

        if not info:
            raise RuntimeError(
                "لم يتمكن yt-dlp من استخراج معلومات الفيديو."
            )

        title = info.get("title") or "فيديو"

        candidates = []

        for item in info.get("requested_downloads") or []:
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
                for path in Path(directory).iterdir()
                if path.is_file()
                and not path.name.endswith(
                    (".part", ".ytdl", ".tmp")
                )
            ]

        if not candidates:
            raise FileNotFoundError(
                "لم يتم العثور على ملف بعد محاولة التنزيل."
            )

        file_path = max(candidates, key=os.path.getsize)

        if os.path.getsize(file_path) == 0:
            raise RuntimeError("الملف الذي تم تنزيله فارغ.")

        return file_path, title


# =====================================================
# إرسال الفيديو للمستخدم
# =====================================================

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
        # المجلد المؤقت يُحذف تلقائيًا بعد انتهاء الإرسال
        with tempfile.TemporaryDirectory(
            prefix="jubouri_"
        ) as temp_dir:

            file_path, title = await asyncio.to_thread(
                download_media,
                url,
                temp_dir,
            )

            size = os.path.getsize(file_path)

            if size > MAX_FILE_SIZE:
                await status.edit_text(
                    "⚠️ تم العثور على الفيديو، لكن حجمه أكبر "
                    "من الحد الاحترازي للإرسال.\n"
                    "جرّب فيديو أقصر أو أقل حجمًا."
                )
                return

            await status.edit_text("📤 تم التنزيل، جارٍ الإرسال...")

            # إرسال MP4 كفيديو، والأنواع الأخرى كملف
            suffix = Path(file_path).suffix.lower()

            with open(file_path, "rb") as media:
                if suffix == ".mp4":
                    await message.reply_video(
                        video=media,
                        caption=f"✅ {title[:800]}",
                        supports_streaming=True,
                        read_timeout=120,
                        write_timeout=120,
                        connect_timeout=30,
                        pool_timeout=30,
                    )
                else:
                    await message.reply_document(
                        document=media,
                        caption=f"✅ {title[:800]}",
                        read_timeout=120,
                        write_timeout=120,
                        connect_timeout=30,
                        pool_timeout=30,
                    )

        await status.delete()

    except Exception as error:
        logger.exception("فشل تنزيل الرابط: %s", url)

        error_text = str(error).lower()

        if (
            "sign in to confirm" in error_text
            or "not a bot" in error_text
        ):
            reply = (
                "⚠️ المنصة تطلب التحقق من الطلب الآلي. "
                "جرّب رابطًا عامًا آخر؛ وقد لا يكفي تحديث المكتبات "
                "لحل هذه القيود."
            )

        elif (
            "unsupported url" in error_text
            or "no suitable extractor" in error_text
        ):
            reply = (
                "❌ لم يتمكن محرك التحميل من التعرف على هذا الرابط. "
                "قد تكون المنصة غير مدعومة أو غيّرت طريقة عرض الفيديو."
            )

        elif (
            "private" in error_text
            or "login required" in error_text
            or "authentication" in error_text
        ):
            reply = (
                "🔒 يبدو أن الفيديو خاص أو يتطلب تسجيل الدخول "
                "ولا يمكن الوصول إليه حاليًا."
            )

        elif (
            "timed out" in error_text
            or "timeout" in error_text
            or "network" in error_text
        ):
            reply = (
                "🌐 تعذر الاتصال بالمنصة. قد تكون هناك مشكلة "
                "مؤقتة في الشبكة أو قيود من الاستضافة."
            )

        else:
            reply = (
                "❌ فشل تحميل الرابط.\n"
                "تم تسجيل تفاصيل الخطأ في Logs لتشخيصه."
            )

        try:
            await status.edit_text(reply)
        except TelegramError:
            logger.exception("تعذر تحديث رسالة حالة التحميل")


# =====================================================
# معالجة أخطاء تيليجرام العامة
# =====================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    error = context.error

    if isinstance(error, Conflict):
        logger.critical(
            "تعارض في استقبال تحديثات تيليجرام. "
            "تأكد من عدم تشغيل نسخة أخرى، ومن عدم إعادة "
            "تفعيل Webhook بواسطة خدمة أخرى."
        )

    elif isinstance(error, NetworkError):
        logger.warning("خطأ اتصال بتيليجرام: %s", error)

    else:
        logger.error(
            "حدث خطأ أثناء معالجة تحديث تيليجرام",
            exc_info=error,
        )


# =====================================================
# إنشاء التطبيق وتشغيله
# =====================================================

def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError(
            "متغير البيئة TELEGRAM_BOT_TOKEN غير موجود. "
            "أضف توكن البوت في إعدادات FadeHost."
        )

    application = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    application.add_handler(
        CommandHandler("start", start_command)
    )
    application.add_handler(
        CommandHandler("stats", stats_command)
    )
    application.add_handler(
        CommandHandler("broadcast", broadcast_command)
    )
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            download_and_send,
        )
    )

    application.add_error_handler(error_handler)

    logger.info("AlJubouriSaveBot starting...")

    # run_polling يدير دورة حياة التطبيق ويبدأ استقبال التحديثات
    application.run_polling(
        drop_pending_updates=False,
        allowed_updates=Update.ALL_TYPES,
    )


if __name__ == "__main__":
    main()
