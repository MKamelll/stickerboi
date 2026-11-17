import asyncio
import os
import subprocess
from pathlib import Path

from telegram import Message, Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
UPLOAD_DIR = BASE_DIR / "cache" / "uploads"
GIFS_DIR = BASE_DIR / "cache" / "gifs"
STICKERS_DIR = BASE_DIR / "cache" / "stickers"
DEFAULT_GIF_DURATION_SECS = 5
DEFAULT_GIF_START_SECS = "00:00:00"
DEFAULT_GIF_SPEEDUP_FACTOR = 2.0
SPEED_UPS = {
    "2.0": "setpts=0.5*PTS",
    "1.5": "setpts=0.67*PTS",
    "1.25": "setpts=0.8*PTS",
}


for i in (UPLOAD_DIR, GIFS_DIR, STICKERS_DIR):
    i.mkdir(parents=True, exist_ok=True)


def convert_mp4_to_gif(input_path: Path, output_path: Path):
    speed_up = SPEED_UPS.get(str(DEFAULT_GIF_SPEEDUP_FACTOR), "")
    cmd = [
        "ffmpeg",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{DEFAULT_GIF_START_SECS}",
        "-t",
        f"{DEFAULT_GIF_DURATION_SECS}",
        "-i",
        f"{input_path}",
        "-vf",
        f"{speed_up},fps=10,scale=360:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=64:stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3:diff_mode=rectangle",
        "-loop",
        "0",
        f"{output_path}",
    ]
    subprocess.run(cmd, check=True)


class VideoMp4Filter(filters.MessageFilter):
    def filter(self, message: Message) -> bool:
        return bool(message.video and message.video.mime_type == "video/mp4")


async def hi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if message := update.message:
        await message.reply_text("fuck off")


async def handle_mp4_to_gif(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or context.user_data is None:
        return
    if "pending_video" not in context.user_data:
        await update.message.reply_text("there's no video sent to be proccessed!")
        return
    await update.message.reply_text("converting to gif, standby for the reply..")
    file_name = context.user_data["pending_video"]
    input_path = UPLOAD_DIR / file_name
    output_path = GIFS_DIR / f"{Path(file_name).stem}.gif"
    await asyncio.to_thread(convert_mp4_to_gif, input_path, output_path)

    with open(output_path, "rb") as result_file:
        await update.message.reply_animation(animation=result_file)


async def handle_mp4(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return
    media = update.message.video or update.message.document
    if not media:
        return

    file_name = media.file_name or f"{media.file_unique_id}.mp4"

    telegram_file = await context.bot.get_file(media.file_id)
    file_path = f"{UPLOAD_DIR}/{file_name}"
    await telegram_file.download_to_drive(custom_path=file_path)
    assert context.user_data is not None
    context.user_data["pending_video"] = file_name
    await update.message.reply_text(
        f"mp4 file saved, for gif send /gif and for a sticker send /sticker"
    )


async def handle_unsupported_filetypes(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    if not update.message:
        return
    await update.message.reply_text(
        "file is not an mp4, either use an mp4 file or fuck off"
    )


if __name__ == "__main__":
    if bot_token := os.getenv("bot_token"):
        app = (
            ApplicationBuilder()
            .token(bot_token)
            .connect_timeout(30)
            .read_timeout(60)
            .write_timeout(60)
            .media_write_timeout(120)
            .build()
        )
        print("the stupid bot is running..")
        app.add_handler(CommandHandler("hi", hi))
        mp4_filter = VideoMp4Filter()
        app.add_handler(MessageHandler(mp4_filter, handle_mp4))

        unsupported_filter = (
            filters.VIDEO
            | filters.Document.ALL
            | filters.PHOTO
            | filters.AUDIO
            | filters.VOICE
            | filters.ANIMATION
        )

        app.add_handler(
            MessageHandler(unsupported_filter, handle_unsupported_filetypes)
        )
        app.add_handler(CommandHandler("gif", handle_mp4_to_gif))
        app.run_polling()
