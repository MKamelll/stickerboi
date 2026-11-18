import asyncio
import os
import subprocess
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
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
DEFAULT_GIF_START_SECS = 0
DEFAULT_GIF_SPEEDUP_FACTOR = 2.0
DEFAULT_GIF_FPS = 10
DEFAULT_GIF_WIDTH = 480
SPEED_UPS = {
    "2.0": "setpts=0.5*PTS",
    "1.5": "setpts=0.67*PTS",
    "1.25": "setpts=0.8*PTS",
}


for i in (UPLOAD_DIR, GIFS_DIR, STICKERS_DIR):
    i.mkdir(parents=True, exist_ok=True)


def build_settings_keyboard(user_data: dict) -> InlineKeyboardMarkup:
    fps = user_data.get("fps", DEFAULT_GIF_FPS)
    width = user_data.get("width", DEFAULT_GIF_WIDTH)
    speed_factor = user_data.get("speed_factor", DEFAULT_GIF_SPEEDUP_FACTOR)
    duration_secs = user_data.get("duration_secs", DEFAULT_GIF_DURATION_SECS)
    start_secs = user_data.get("start_secs", DEFAULT_GIF_START_SECS)
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(f"fps: {fps}", callback_data="toggle_fps"),
                InlineKeyboardButton(f"width: {width}", callback_data="toggle_width"),
                InlineKeyboardButton(
                    f"speed: {speed_factor}", callback_data="toggle_speed"
                ),
                InlineKeyboardButton(
                    f"duration (secs): {duration_secs}", callback_data="toggle_duration"
                ),
                InlineKeyboardButton(
                    f"start point (secs): {start_secs}", callback_data="toggle_start"
                ),
            ],
            [InlineKeyboardButton("convert", callback_data="start_converting")],
        ]
    )


async def handle_settings_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not isinstance(query.message, Message):
        return
    await query.answer()
    if context.user_data is None:
        return
    match query.data:
        case "toggle_fps":
            fps_options = [10, 12, 15, 24]
            current = context.user_data.get("fps", DEFAULT_GIF_FPS)
            context.user_data["fps"] = fps_options[
                (fps_options.index(current) + 1) % len(fps_options)
            ]
            await query.edit_message_reply_markup(
                reply_markup=build_settings_keyboard(context.user_data)
            )

        case "toggle_width":
            width_options = [480, 320]
            current = context.user_data.get("width", DEFAULT_GIF_WIDTH)
            context.user_data["width"] = width_options[
                (width_options.index(current) + 1) % len(width_options)
            ]
            await query.edit_message_reply_markup(
                reply_markup=build_settings_keyboard(context.user_data)
            )
        case "toggle_speed":
            speed_options = [1.25, 1.5, 2.0]
            current = context.user_data.get("speed_factor", DEFAULT_GIF_SPEEDUP_FACTOR)
            context.user_data["speed_factor"] = speed_options[
                (speed_options.index(current) + 1) % len(speed_options)
            ]
            await query.edit_message_reply_markup(
                reply_markup=build_settings_keyboard(context.user_data)
            )

        case "toggle_duration":
            duration_options = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60]
            current = context.user_data.get("duration_secs", DEFAULT_GIF_DURATION_SECS)
            context.user_data["duration_secs"] = duration_options[
                (duration_options.index(current) + 1) % len(duration_options)
            ]
            await query.edit_message_reply_markup(
                reply_markup=build_settings_keyboard(context.user_data)
            )

        case "toggle_start":
            start_options = [0, 5, 10, 15, 30, 60]
            current = context.user_data.get("start_secs", DEFAULT_GIF_START_SECS)
            context.user_data["start_secs"] = start_options[
                (start_options.index(current) + 1) % len(start_options)
            ]
            await query.edit_message_reply_markup(
                reply_markup=build_settings_keyboard(context.user_data)
            )
        case "start_converting":
            if "pending_video" not in context.user_data:
                await query.edit_message_text("there's no video sent to be proccessed!")
                return
            file_name = context.user_data["pending_video"]
            input_path = UPLOAD_DIR / file_name
            output_path = GIFS_DIR / f"{Path(file_name).stem}.gif"
            fps = context.user_data.get("fps", DEFAULT_GIF_FPS)
            width = context.user_data.get("width", DEFAULT_GIF_WIDTH)
            speed_factor = context.user_data.get(
                "speed_factor", DEFAULT_GIF_SPEEDUP_FACTOR
            )
            duration_secs = context.user_data.get(
                "duration_secs", DEFAULT_GIF_DURATION_SECS
            )
            start_secs = context.user_data.get("start_secs", DEFAULT_GIF_START_SECS)

            await query.edit_message_text(
                f"converting to gif (width: {width}, FPS: {fps}, speed: {speed_factor}, duration (secs): {duration_secs}, start (secs): {start_secs})..."
            )

            await asyncio.to_thread(
                convert_mp4_to_gif,
                input_path,
                output_path,
                {
                    "fps": fps,
                    "width": width,
                    "speed_factor": speed_factor,
                    "duration_secs": duration_secs,
                    "start_secs": start_secs,
                },
            )
            with open(output_path, "rb") as result_file:
                await query.message.reply_animation(animation=result_file)

            await query.edit_message_text("Done!")


def convert_mp4_to_gif(input_path: Path, output_path: Path, options: dict):
    fps = options.get("fps", DEFAULT_GIF_FPS)
    width = options.get("width", DEFAULT_GIF_WIDTH)
    speed_factor = options.get("speed_factor", DEFAULT_GIF_SPEEDUP_FACTOR)
    duration_secs = options.get("duration_secs", DEFAULT_GIF_DURATION_SECS)
    start_secs = options.get("start_secs", DEFAULT_GIF_START_SECS)
    speed_up = SPEED_UPS.get(str(speed_factor), "")
    cmd = [
        "ffmpeg",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{start_secs}",
        "-t",
        f"{duration_secs}",
        "-i",
        f"{input_path}",
        "-vf",
        f"{speed_up},fps={fps},scale={width}:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=64:stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=3:diff_mode=rectangle",
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
    context.user_data["fps"] = DEFAULT_GIF_FPS
    context.user_data["width"] = DEFAULT_GIF_WIDTH
    context.user_data["speed_factor"] = DEFAULT_GIF_SPEEDUP_FACTOR
    context.user_data["duration_secs"] = DEFAULT_GIF_DURATION_SECS
    context.user_data["start_secs"] = DEFAULT_GIF_START_SECS

    await update.message.reply_text(
        f"mp4 file saved, pick your settings below and tap convert:",
        reply_markup=build_settings_keyboard(context.user_data),
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
        app.add_handler(CallbackQueryHandler(handle_settings_button))
        app.run_polling()
