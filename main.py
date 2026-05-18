"""
VoxCPM Voice Clone — Telegram Bot
===================================
មុខងារ: បន្ទោតសំឡេង (Clone Voice) តែមួយ
ភាសា UI: ខ្មែរ
"""

import io
import logging
import os
import tempfile
import traceback

import soundfile as sf
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode, ChatAction
from telegram.request import HTTPXRequest
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from pydub import AudioSegment


# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8838385256:AAGKNfpdAmP6YP2tLhejNvd4Gza2MIUqYwQ")

# ── Global Model ───────────────────────────────────────────────────────────
tts = None
MODEL_OK = False
SAMPLE_RATE = 48000

# ── Lazy load — runs after bot connects to Telegram ───────────────────────
async def load_model(application: Application):
    global tts, MODEL_OK, SAMPLE_RATE
    logger.info("កំពុងផ្ទុក VoxCPM2 model...")
    try:
        from voxcpm import VoxCPM
        tts = VoxCPM.from_pretrained("openbmb/VoxCPM2", load_denoiser=False)
        SAMPLE_RATE = tts.tts_model.sample_rate
        MODEL_OK = True
        logger.info(f"VoxCPM2 រួចរាល់! Sample rate: {SAMPLE_RATE} Hz")
    except Exception as e:
        logger.error(f"មិនអាចផ្ទុកម៉ូដែល: {e}")
        MODEL_OK = False

# ── States ────────────────────────────────────────────────────────────────
STATE_MENU, STATE_WAIT_AUDIO, STATE_WAIT_TEXT, STATE_WAIT_STYLE = range(4)

KEY_REF_PATH = "ref_path"
KEY_TEXT     = "text"
KEY_STYLE    = "style"


# ── Keyboards ──────────────────────────────────────────────────────────────
def menu_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎙 CLONE VOICE   START ", callback_data="start_clone")],
        [InlineKeyboardButton("📖 ជំនួយ & របៀបប្រើ 📖",       callback_data="help")],
    ])

def skip_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⏭ រំលង Style  [ SKIP ]", callback_data="skip_style")],
    ])

# ── UI Text — Premium Style ────────────────────────────────────────────────
TXT_WELCOME = (
    "▰▰▰▰▰▰▰▰▰▰▰▰▰\n"
    "🌟  *CloneVoiceKH Bot*  🌟\n"
    "▰▰▰▰▰▰▰▰▰▰▰▰▰\n\n"
    "「 🤖 *AI Voice Cloning* 」\n"
    "Copy សំឡេងណាមួយ · និយាយអត្ថបទថ្មី ✨\n\n"
    "━━━━ 📌 *របៀបប្រើ* ━━━━\n"
    "  ❶  ផ្ញើ *សំឡេង* ដែលចង់ Copy\n"
    "  ❷  វាយ *អត្ថបទ* ចង់អោយ AI និយាយ\n"
    "  ❸  ជ្រើស *Style* _(ឬរំលង)_\n"
    "  ❹  ទទួល *សំឡេង Clone* ✅\n"
    "━━━━━━━━━━━━━━━━━━━━\n\n"
    "👇 *ចុចប៊ូតុងខាងក្រោម ដើម្បីចាប់ផ្តើម*"
)

TXT_HELP = (
    "▰▰▰▰▰▰▰▰▰▰▰▰▰\n"
    "📖  *HELP & GUIDE*  📖\n"
    "▰▰▰▰▰▰▰▰▰▰▰▰▰\n\n"
    "🎙 *សំឡេងល្អបំផុត:*\n"
    "  ◆ ប្រវែង *5–15 វិនាទី*\n"
    "  ◆ ស្អាត · គ្មានសំឡេងរំខាន\n"
    "🎨 *Style ឧទាហរណ៍:*\n"
    "`យឺតៗ` · `លឿន, រីករាយ` · `ស្រទន់` · `ខ្លាំង, ច្បាស់`\n"
    "EN: `slowly` · `cheerful` · `serious`\n\n"
    "⏱ *ពេលវេលា:* 1–3 នាទី\n\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "▸ */start* — ត្រឡប់ទៅម៉ឺនុយ\n"
    "▸ */cancel* — បោះបង់ Session"
)

TXT_MODEL_LOADING = (
    "▰▰▰▰▰▰▰▰▰▰▰▰▰\n"
    "⚙️  *SYSTEM LOADING...*  ⚙️\n"
    "▰▰▰▰▰▰▰▰▰▰▰▰▰\n\n"
    "⏳ AI Model កំពុងចាប់ផ្តើម\n"
    "សូមរង់ចាំ 1 នាទី ហើយព្យាយាមម្តងទៀត 🙏"
)

TXT_SEND_AUDIO = (
    "▰▰▰▰▰▰▰▰▰▰▰▰▰\n"
    "🎙  *STEP  1 / 3  —  AUDIO*  🎙\n"
    "▰▰▰▰▰▰▰▰▰▰▰▰▰\n\n"
    "📤 ផ្ញើ *សំឡេង* ដែលចង់ Clone:\n\n"
    "  ◆ Voice message ឬ Audio file\n"
    "  ◆ Format: `.wav` · `.mp3` · `.ogg`\n"
    "  ◆ ⏱ 5–15 វិនាទី · ស្អាត"
)

TXT_AUDIO_RECEIVED = (
    "✅ *ទទួលបានសំឡេងរួច!* ✅\n\n"
    "▰▰▰▰▰▰▰▰▰▰▰▰▰\n"
    "✏️  *STEP  2 / 3  —  TEXT*  ✏️\n"
    "▰▰▰▰▰▰▰▰▰▰▰▰▰\n\n"
    "📝 វាយ *អត្ថបទ* ចង់អោយ AI និយាយ:\n"
    "_(ខ្មែរ · English · ភាសាផ្សេង)_"
)

TXT_SEND_STYLE = (
    "▰▰▰▰▰▰▰▰▰▰▰▰▰\n"
    "🎨  *STEP  3 / 3  —  STYLE*  🎨\n"
    "▰▰▰▰▰▰▰▰▰▰▰▰▰\n\n"
    "💡 ត្រូវការ Style? វាយ ឬចុច *Skip*\n\n"
    "  ◆ `យឺតៗ, ស្រទន់`\n"
    "  ◆ `cheerful, fast`\n"
    "  ◆ `serious, clear`"
)

TXT_GENERATING = (
    "▰▰▰▰▰▰▰▰▰▰▰▰▰\n"
    "🔄  *AI GENERATING...*  🔄\n"
    "▰▰▰▰▰▰▰▰▰▰▰▰▰\n\n"
    "⚡ AI កំពុងបង្កើតសំឡេង...\n"
    "⏱ សូមរង់ចាំ *1–3 នាទី*\n"
    "🙏 កុំបិទ Bot ក្នុងពេលនេះ"
)

TXT_DONE    = "▰▰▰▰▰▰▰▰▰▰▰▰▰\n✅ <b>CLONE SUCCESS!</b> ✅\n▰▰▰▰▰▰▰▰▰▰▰▰▰\n\n🤖 បង្កើតដោយ @CloneVoiceKH_Bot"
TXT_ERROR   = "▰▰▰▰▰▰▰▰▰▰▰▰▰\n❌ *ERROR* ❌\n▰▰▰▰▰▰▰▰▰▰▰▰▰\n\nមានបញ្ហា · ផ្ញើ /start ហើយព្យាយាមម្តងទៀត"
TXT_NO_AUDIO= "⚠️ *សូមផ្ញើ Voice message ឬ Audio file ប៉ុណ្ណោះ*"
TXT_AGAIN   = "🔁 *ចង់ Clone ម្តងទៀតទេ?* 🔁"
TXT_CANCEL  = "◈ បោះបង់រួច · វាយ /start ដើម្បីចាប់ផ្តើម"
TXT_FALLBACK= "🤔 វាយ /start ដើម្បីចាប់ផ្តើម"
# ── Helpers ────────────────────────────────────────────────────────────────
async def save_audio(file_obj) -> str:
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".wav")
    await file_obj.download_to_drive(tmp.name)
    tmp.close()
    return tmp.name

def cleanup(user_data: dict):
    path = user_data.pop(KEY_REF_PATH, None)
    if path and os.path.exists(path):
        try:
            os.remove(path)
        except:
            pass
    user_data.pop(KEY_TEXT, None)
    user_data.pop(KEY_STYLE, None)

def run_tts(text: str, ref_path: str, style: str = "") -> bytes:
    if not MODEL_OK:
        raise RuntimeError("Model not ready")
    final_text = f"({style}){text}" if style else text
    wav = tts.generate(
        text=final_text,
        reference_wav_path=ref_path,
        cfg_value=2.0,
        inference_timesteps=10,
    )
    buf = io.BytesIO()
    sf.write(buf, wav, SAMPLE_RATE, format="WAV")
    buf.seek(0)
    return buf.read()

async def send_result(chat_id: int, wav_data: bytes, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        # ១. បំប្លែងពី WAV Bytes ទៅជា MP3
        wav_io = io.BytesIO(wav_data)
        audio = AudioSegment.from_wav(wav_io)
        
        mp3_io = io.BytesIO()
        audio.export(
    mp3_io, 
    format="mp3", 
    bitrate="192k", 
    parameters=["-ar", "44100"] # បន្ថែមជួរនេះ ដើម្បីឱ្យ Messenger ស្គាល់ច្បាស់
)
        mp3_io.seek(0)
        
        final_mp3 = mp3_io.read()

        # ២. ផ្ញើជា Voice Message (ប្តូរទៅប្រើ HTML)
        await ctx.bot.send_voice(
            chat_id=chat_id,
            voice=io.BytesIO(final_mp3),
            caption=TXT_DONE,
            parse_mode=ParseMode.HTML,  # ប្តូរពី MARKDOWN ទៅ HTML
        )

        # ៣. ផ្ញើជាឯកសារ MP3 (ប្តូរទៅប្រើ HTML)
        await ctx.bot.send_document(
            chat_id=chat_id,
            document=io.BytesIO(final_mp3),
            filename="clone_output.mp3",
            caption="📥 <b>ទាញយក MP3 (192kbps)</b>", # ប្រើ HTML tag <b>
            parse_mode=ParseMode.HTML, # ប្តូរពី MARKDOWN ទៅ HTML
        )
    except Exception as e:
        logger.error(f"Error in send_result: {e}")
# ── Command handlers ───────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    cleanup(ctx.user_data)
    if not MODEL_OK:
        await update.message.reply_text(TXT_MODEL_LOADING, parse_mode=ParseMode.MARKDOWN)
        return STATE_MENU
    await update.message.reply_text(
        TXT_WELCOME, parse_mode=ParseMode.MARKDOWN, reply_markup=menu_kb()
    )
    return STATE_MENU

async def cmd_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    cleanup(ctx.user_data)
    await update.message.reply_text(TXT_CANCEL)
    return ConversationHandler.END

# ── Menu callback ──────────────────────────────────────────────────────────
async def cb_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()

    if query.data == "help":
        await query.message.reply_text(TXT_HELP, parse_mode=ParseMode.MARKDOWN)
        return STATE_MENU

    if query.data == "start_clone":
        if not MODEL_OK:
            await query.message.reply_text(TXT_MODEL_LOADING, parse_mode=ParseMode.MARKDOWN)
            return STATE_MENU
        await query.message.reply_text(TXT_SEND_AUDIO, parse_mode=ParseMode.MARKDOWN)
        return STATE_WAIT_AUDIO

    return STATE_MENU

# ── Step 1: Receive audio ──────────────────────────────────────────────────
async def got_audio(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    msg = update.message
    audio = (
        msg.voice
        or msg.audio
        or (msg.document if msg.document
            and "audio" in (msg.document.mime_type or "") else None)
    )
    if not audio:
        await msg.reply_text(TXT_NO_AUDIO, parse_mode=ParseMode.MARKDOWN)
        return STATE_WAIT_AUDIO

    file = await ctx.bot.get_file(audio.file_id)
    ctx.user_data[KEY_REF_PATH] = await save_audio(file)
    await msg.reply_text(TXT_AUDIO_RECEIVED, parse_mode=ParseMode.MARKDOWN)
    return STATE_WAIT_TEXT

# ── Step 2: Receive text ───────────────────────────────────────────────────
async def got_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data[KEY_TEXT] = update.message.text.strip()
    await update.message.reply_text(
        TXT_SEND_STYLE, parse_mode=ParseMode.MARKDOWN, reply_markup=skip_kb()
    )
    return STATE_WAIT_STYLE

# ── Step 3a: Style typed ───────────────────────────────────────────────────
async def got_style(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data[KEY_STYLE] = update.message.text.strip()
    return await _generate(update.message.chat_id, update.message, ctx)

# ── Step 3b: Skip style button ────────────────────────────────────────────
async def cb_skip(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    ctx.user_data[KEY_STYLE] = ""
    return await _generate(query.message.chat_id, None, ctx)

# ── Core generation ────────────────────────────────────────────────────────
async def _generate(chat_id: int, msg, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    await ctx.bot.send_chat_action(chat_id=chat_id, action=ChatAction.RECORD_VOICE)
    status = await ctx.bot.send_message(
        chat_id=chat_id, text=TXT_GENERATING, parse_mode=ParseMode.MARKDOWN
    )
    try:
        wav_data = run_tts(
            text=ctx.user_data.get(KEY_TEXT, ""),
            ref_path=ctx.user_data.get(KEY_REF_PATH, ""),
            style=ctx.user_data.get(KEY_STYLE, ""),
        )
        await send_result(chat_id, wav_data, ctx)
    except Exception:
        logger.error(traceback.format_exc())
        await ctx.bot.send_message(
            chat_id=chat_id, text=TXT_ERROR, parse_mode=ParseMode.MARKDOWN
        )
    finally:
        try:
            await status.delete()
        except:
            pass
        cleanup(ctx.user_data)

    await ctx.bot.send_message(
        chat_id=chat_id, text=TXT_AGAIN,
        parse_mode=ParseMode.MARKDOWN, reply_markup=menu_kb()
    )
    return STATE_MENU

# ── Fallback ───────────────────────────────────────────────────────────────
async def fallback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(TXT_FALLBACK)
    return STATE_MENU

# ── Main ───────────────────────────────────────────────────────────────────
def main():
    request = HTTPXRequest(
        connect_timeout=60,
        read_timeout=120,
        write_timeout=120,
    )

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .request(request)
        .build()
    )

    # Load model after bot connects (avoids startup timeout)
    app.post_init = load_model

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start)],
        states={
            STATE_MENU: [
                CallbackQueryHandler(cb_menu),
            ],
            STATE_WAIT_AUDIO: [
                MessageHandler(
                    filters.VOICE | filters.AUDIO | filters.Document.ALL,
                    got_audio,
                ),
            ],
            STATE_WAIT_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, got_text),
            ],
            STATE_WAIT_STYLE: [
                CallbackQueryHandler(cb_skip, pattern="^skip_style$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, got_style),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cmd_cancel),
            MessageHandler(filters.ALL, fallback),
        ],
        allow_reentry=True,
    )

    app.add_handler(conv)
    logger.info("Bot កំពុងដំណើរការ... 🚀")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
