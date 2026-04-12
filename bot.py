import os
import re
import uuid
import tempfile
import asyncio
from collections import deque
from threading import Thread
from flask import Flask

import discord
from discord.ext import commands
from gtts import gTTS
from dotenv import load_dotenv

print("BOT.PY STARTING...")

load_dotenv()

# ==========================================
# WEB SERVER (Chống sập Render)
# ==========================================
app = Flask(__name__)
@app.route('/')
def home():
    return "Bot hoạt động hoàn hảo!"

@app.route('/healthz')
def healthz():
    return "OK"

def run_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

# Khởi chạy web server ngầm ngay khi start
Thread(target=run_server, daemon=True).start()
# ==========================================

TOKEN = os.getenv("DISCORD_TOKEN")
print("DISCORD_TOKEN exists:", bool(TOKEN))

FFMPEG_PATH = "ffmpeg"
GUILD_ID = 1440581960069287939
MY_GUILD = discord.Object(id=GUILD_ID)

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

AUTO_TTS = False
TTS_TEXT_CHANNEL_ID = None
tts_queue = deque()
is_speaking = False


def clean_text(text: str) -> str:
    text = re.sub(r"http\S+", "", text)
    text = re.sub(r"<@!?\d+>", "", text)
    text = re.sub(r"[^\w\sÀ-ỹ]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def add_to_queue(vc: discord.VoiceClient, text: str):
    text = clean_text(text)
    if not text:
        return
    tts_queue.append((vc, text))
    asyncio.create_task(play_next())


async def generate_tts_file(text: str, filename: str):
    def _save():
        gTTS(text=text, lang="vi").save(filename)

    await asyncio.to_thread(_save)


async def play_next():
    global is_speaking

    if is_speaking:
        return

    if not tts_queue:
        return

    is_speaking = True

    try:
        while tts_queue:
            vc, text = tts_queue.popleft()

            if not vc or not vc.is_connected():
                print("Skip queue item: voice client not connected")
                continue

            filename = os.path.join(tempfile.gettempdir(), f"tts_{uuid.uuid4().hex}.mp3")

            try:
                print("Generating TTS:", text)
                await asyncio.wait_for(generate_tts_file(text, filename), timeout=20)

                if not vc.is_connected():
                    print("Voice disconnected before play")
                    try:
                        if os.path.exists(filename):
                            os.remove(filename)
                    except Exception:
                        pass
                    continue

                finished = asyncio.Event()

                source = discord.FFmpegPCMAudio(
                    filename,
                    executable=FFMPEG_PATH,
                    options="-vn"
                )

                def after_play(err):
                    if err:
                        print("FFmpeg after_play error:", repr(err))

                    try:
                        if os.path.exists(filename):
                            os.remove(filename)
                    except Exception as cleanup_error:
                        print("Cleanup error:", repr(cleanup_error))

                    bot.loop.call_soon_threadsafe(finished.set)

                print("Start playing audio")
                vc.play(source, after=after_play)
                await finished.wait()
                print("Finished playing audio")

            except asyncio.TimeoutError:
                print("TTS timeout for text:", text)
                try:
                    if os.path.exists(filename):
                        os.remove(filename)
                except Exception:
                    pass
            except Exception as e:
                print("Lỗi TTS:", repr(e))
                try:
                    if os.path.exists(filename):
                        os.remove(filename)
                except Exception:
                    pass

    finally:
        is_speaking = False


@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync(guild=MY_GUILD)
        print(f"Bot online: {bot.user} | synced {len(synced)} commands (guild)")
    except Exception as e:
        print("Sync slash lỗi:", repr(e))


@bot.event
async def on_disconnect():
    print("Bot bị ngắt kết nối Discord")


@bot.event
async def on_resumed():
    print("Bot đã reconnect lại Discord")


@bot.event
async def on_voice_state_update(member, before, after):
    if bot.user and member.id == bot.user.id:
        before_name = before.channel.name if before.channel else None
        after_name = after.channel.name if after.channel else None
        print(f"VOICE UPDATE: {before_name} -> {after_name}")


@bot.tree.command(name="join", description="Gọi bot vào phòng voice", guild=MY_GUILD)
async def join(interaction: discord.Interaction):
    if not interaction.user.voice:
        await interaction.response.send_message("Bạn cần vào voice trước", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    channel = interaction.user.voice.channel
    vc = interaction.guild.voice_client

    try:
        if not vc:
            print(f"Connecting to voice: {channel.name}")
            await channel.connect(self_deaf=True)
        elif vc.channel != channel:
            print(f"Moving voice: {vc.channel.name} -> {channel.name}")
            await vc.move_to(channel)

        await interaction.followup.send(f"Bot đã vào {channel.name}", ephemeral=True)
    except Exception as e:
        print("JOIN ERROR:", repr(e))
        await interaction.followup.send(f"Lỗi vào voice: {e}", ephemeral=True)


@bot.tree.command(name="n", description="Bot nói nội dung bạn nhập", guild=MY_GUILD)
async def n(interaction: discord.Interaction, text: str):
    global TTS_TEXT_CHANNEL_ID

    if not interaction.user.voice:
        await interaction.response.send_message("Bạn cần vào voice trước", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True)

    TTS_TEXT_CHANNEL_ID = interaction.channel.id
    channel = interaction.user.voice.channel
    vc = interaction.guild.voice_client

    try:
        if not vc:
            print(f"Connecting for /n: {channel.name}")
            vc = await channel.connect(self_deaf=True)
        elif vc.channel != channel:
            print(f"Moving for /n: {vc.channel.name} -> {channel.name}")
            await vc.move_to(channel)

        add_to_queue(vc, text)
        await interaction.followup.send("Đang đọc...", ephemeral=True)
    except Exception as e:
        print("N COMMAND ERROR:", repr(e))
        await interaction.followup.send(f"Lỗi đọc: {e}", ephemeral=True)


@bot.tree.command(name="auto", description="Bật tự động đọc tin nhắn", guild=MY_GUILD)
async def auto(interaction: discord.Interaction):
    global AUTO_TTS
    AUTO_TTS = True
    await interaction.response.send_message("AUTO TTS: BẬT", ephemeral=True)


@bot.tree.command(name="tat", description="Tắt tự động đọc", guild=MY_GUILD)
async def tat(interaction: discord.Interaction):
    global AUTO_TTS
    AUTO_TTS = False
    await interaction.response.send_message("AUTO TTS: TẮT", ephemeral=True)


@bot.tree.command(name="skip", description="Bỏ câu đang đọc", guild=MY_GUILD)
async def skip(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.stop()
        await interaction.followup.send("Đã skip", ephemeral=True)
    else:
        await interaction.followup.send("Bot không nói", ephemeral=True)


@bot.tree.command(name="out", description="Đá bot ra khỏi voice", guild=MY_GUILD)
async def out(interaction: discord.Interaction):
    global is_speaking
    await interaction.response.defer(ephemeral=True)

    vc = interaction.guild.voice_client
    if vc:
        tts_queue.clear()
        is_speaking = False

        if vc.is_playing():
            vc.stop()

        try:
            await vc.disconnect(force=True)
            await interaction.followup.send("Bot đã thoát", ephemeral=True)
        except Exception as e:
            print("OUT ERROR:", repr(e))
            await interaction.followup.send(f"Lỗi thoát voice: {e}", ephemeral=True)
    else:
        await interaction.followup.send("Bot chưa vào voice", ephemeral=True)


@bot.tree.command(name="reset", description="Làm mới bot khi bị đơ/lag", guild=MY_GUILD)
async def reset_bot(interaction: discord.Interaction):
    global is_speaking, AUTO_TTS, TTS_TEXT_CHANNEL_ID

    await interaction.response.defer(ephemeral=True)

    tts_queue.clear()
    is_speaking = False
    AUTO_TTS = False
    TTS_TEXT_CHANNEL_ID = None

    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.stop()

    await interaction.followup.send(
        "Đã dọn dẹp hệ thống! Bot vẫn ở trong phòng, bạn có thể chat tiếp.",
        ephemeral=True
    )


@bot.event
async def on_message(message: discord.Message):
    await bot.process_commands(message)

    if message.author.bot or not AUTO_TTS:
        return

    if not message.guild or not message.content.strip():
        return

    if TTS_TEXT_CHANNEL_ID and message.channel.id != TTS_TEXT_CHANNEL_ID:
        return

    vc = message.guild.voice_client
    if not vc or not message.author.voice or message.author.voice.channel != vc.channel:
        return

    add_to_queue(vc, message.content)


async def main():
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN không tồn tại hoặc đang rỗng")

    print("Starting Discord bot...")
    async with bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print("BOT CRASH:", repr(e))
        raise
