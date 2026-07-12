import os
import logging
import calibre as cb
from dotenv import load_dotenv, find_dotenv
from telegram import Update
from telegram.ext import (
    filters,
    MessageHandler,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

load_dotenv(find_dotenv())

_raw_allowed_user_id = os.getenv("USER_ID")

if _raw_allowed_user_id is None:
    raise RuntimeError("ALLOWED_USER_ID environment variable is not set")

ALLOWED_USER_ID: int = int(_raw_allowed_user_id)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)

TYPES_ACCEPTED = [".pdf", ".epub", ".txt", ".mobi", ".azw3", ".cbz", ".cbr"]


def _is_authorized(user) -> bool:
    return user is not None and user.id == ALLOWED_USER_ID


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_message = (
        "👋 Welcome to *kind3Bot*! 📚\n\n"
        "I help you get eBooks into your Calibre-Web library. Pick an "
        "action first, then send me the file:\n\n"
        "• /convert — convert a file to EPUB and add it to your library\n"
        "• /fanfic — format a raw AO3 FanFic and add it to your library\n"
        "• /library — send a file straight to your library, no conversion\n"
        "• /cancel — cancel the pending action\n\n"
        "Use /help for details on each one. 😊"
    )
    if update.effective_chat:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=welcome_message,
            parse_mode="Markdown",
        )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_message = (
        "📖 *kind3Bot Help* 📖\n\n"
        "1. */convert*\n"
        "   - Run the command, then send the file.\n"
        "   - I'll convert it to EPUB and add it to your library.\n\n"
        "2. */fanfic Title - Author - Series[extra]*\n"
        "   - Run the command with the metadata as arguments, then send "
        "the raw AO3 file.\n"
        "   - I'll format it, generate a cover, and add it to your "
        "library.\n\n"
        "3. */library*\n"
        "   - Run the command, then send the file.\n"
        "   - I'll drop it into Calibre-Web with no conversion.\n\n"
        "4. */cancel*\n"
        "   - Cancels a pending action.\n\n"
        f"*Supported file types*: {', '.join(TYPES_ACCEPTED)}\n\n"
        "If you encounter any issues, feel free to reach out. Happy "
        "reading! 📚"
    )
    if update.effective_chat:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=help_message,
            parse_mode="Markdown",
        )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("pending_action", None)
    context.user_data.pop("fanfic_name", None)
    if update.effective_chat:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="❌ Pending action cancelled.",
        )


async def convert_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if not chat:
        return
    if not _is_authorized(user):
        await context.bot.send_message(chat_id=chat.id, text="🚫 Access denied.")
        return
    context.user_data["pending_action"] = "convert"
    await context.bot.send_message(
        chat_id=chat.id, text="📥 Send me the file you want to convert to EPUB."
    )


async def library_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if not chat:
        return
    if not _is_authorized(user):
        await context.bot.send_message(chat_id=chat.id, text="🚫 Access denied.")
        return
    context.user_data["pending_action"] = "library"
    await context.bot.send_message(
        chat_id=chat.id,
        text="📥 Send me the file you want to add to your library.",
    )


async def fanfic_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat = update.effective_chat
    if not chat:
        return
    if not _is_authorized(user):
        await context.bot.send_message(chat_id=chat.id, text="🚫 Access denied.")
        return

    if not context.args:
        await context.bot.send_message(
            chat_id=chat.id,
            text="❌ Usage: /fanfic Title - Author - Series[extra]",
        )
        return

    fanfic_name = " ".join(context.args)
    context.user_data["pending_action"] = "fanfic"
    context.user_data["fanfic_name"] = fanfic_name
    await context.bot.send_message(
        chat_id=chat.id,
        text=f"📥 Got it: *{fanfic_name}*.\nNow send me the raw FanFic file.",
        parse_mode="Markdown",
    )


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    chat = update.effective_chat
    user = update.effective_user

    if not message or not chat or not user:
        return

    if not _is_authorized(user):
        await context.bot.send_message(
            chat_id=chat.id,
            text="🚫 Access denied. You are not authorized to use this bot.",
        )
        return

    document = message.document
    if not document:
        return

    pending_action = context.user_data.get("pending_action")
    if not pending_action:
        await context.bot.send_message(
            chat_id=chat.id,
            text="❌ Please choose an action first: /convert, /fanfic, or "
            "/library.",
        )
        return

    book_name = document.file_name or "unknown"
    book_type = book_name[book_name.rfind(".") :]

    try:
        book_file = await context.bot.get_file(document.file_id)

        if pending_action == "convert":
            if book_type == ".epub":
                await context.bot.send_message(
                    chat_id=chat.id,
                    text="ℹ️ That's already an EPUB — use /library instead.",
                )
            else:
                book_path = f"books/random/{book_name}"
                only_name = cb.get_name(book_path)
                await book_file.download_to_drive(book_path)
                cb.convert_to_epub(book_path, only_name)
                await context.bot.send_message(
                    chat_id=chat.id,
                    text="✅ Converted to EPUB and sent to your library. "
                    "It should appear in Calibre-Web shortly. - kind3Bot",
                )

        elif pending_action == "fanfic":
            fanfic_name = context.user_data.get("fanfic_name")
            fanfic_path = f"books/random/raw/{fanfic_name}"
            await book_file.download_to_drive(fanfic_path)
            cb.tranform_fanfic(fanfic_path, fanfic_name)
            await context.bot.send_message(
                chat_id=chat.id,
                text="✅ FanFic processed and sent to your library. It "
                "should appear in Calibre-Web shortly. - kind3Bot",
            )

        elif pending_action == "library":
            if book_type not in TYPES_ACCEPTED:
                await context.bot.send_message(
                    chat_id=chat.id,
                    text=f"❌ Unsupported format {book_type}. Accepted: "
                    f"{', '.join(TYPES_ACCEPTED)}",
                )
            else:
                await cb.send_to_library(book_file, book_name)
                await context.bot.send_message(
                    chat_id=chat.id,
                    text="✅ File sent directly to your library, no "
                    "conversion applied. It should appear in Calibre-Web "
                    "shortly. - kind3Bot",
                )

    except cb.ConversionError as e:
        await context.bot.send_message(
            chat_id=chat.id, text=f"❌ Error during conversion: {e}"
        )
    except cb.FanficProcessingError as e:
        await context.bot.send_message(
            chat_id=chat.id, text=f"❌ Error processing FanFic: {e}"
        )
    except Exception as e:
        await context.bot.send_message(
            chat_id=chat.id, text=f"❌ An unexpected error occurred: {e}"
        )
    finally:
        context.user_data.pop("pending_action", None)
        context.user_data.pop("fanfic_name", None)


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if not chat:
        return

    await context.bot.send_message(
        chat_id=chat.id,
        text="Sorry, I didn't understand that command.",
    )


if __name__ == "__main__":
    bot_token = os.getenv("TOKEN_TELEGRAM")

    if bot_token is None:
        raise RuntimeError("TOKEN_TELEGRAM environment variable is not set")

    application = ApplicationBuilder().token(bot_token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_cmd))
    application.add_handler(CommandHandler("convert", convert_cmd))
    application.add_handler(CommandHandler("library", library_cmd))
    application.add_handler(CommandHandler("fanfic", fanfic_cmd))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(
        MessageHandler(filters.Document.ALL & (~filters.COMMAND), handle_document)
    )
    application.add_handler(MessageHandler(filters.COMMAND, unknown))

    application.run_polling()
