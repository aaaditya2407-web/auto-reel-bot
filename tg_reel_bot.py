import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from auto_topic import generate_video

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎬 *Auto Reel Generator Ready!*\nSend `/reel <topic>` (e.g., `/reel How Bitcoin Mining Works`)",
        parse_mode="Markdown"
    )

async def make_reel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = " ".join(context.args).strip()
    if not topic:
        await update.message.reply_text("Usage: `/reel How UPI works`", parse_mode="Markdown")
        return

    status_msg = await update.message.reply_text(f"⚙️ Generating video for: *{topic}*...\n(Takes ~25 seconds)", parse_mode="Markdown")
    try:
        mp4_path = await generate_video(topic)
        await status_msg.edit_text("📤 Uploading video to Telegram...")
        with open(mp4_path, "rb") as vid:
            await update.message.reply_video(video=vid, caption=f"✅ *{topic}*", parse_mode="Markdown")
        await status_msg.delete()
    except Exception as e:
        await status_msg.edit_text(f"❌ Error: `{e}`", parse_mode="Markdown")

if __name__ == "__main__":
    if not BOT_TOKEN:
        raise ValueError("Set TELEGRAM_BOT_TOKEN first!")
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reel", make_reel))
    print("🤖 Telegram Reel Bot is live! Send /reel <topic> to your bot.")
    app.run_polling()
