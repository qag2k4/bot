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

load_dotenv()

# ==========================================
# WEB SERVER
# ==========================================
app = Flask(__name__)
@app.route('/')
def home(): return "Bot Live!"

@app.route('/healthz')
def healthz(): return "OK"

def run_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

Thread(target=run_server, daemon=True).start()

# ==========================================
# CẤU HÌNH BOT
# ==========================================
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1440581960069287939 
MY_GUILD = discord.Object(id=GUILD_ID)

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

tts_queue = deque()
is_speaking = False

def clean_text(text: str) -> str:
    text = re.sub(r"http\S+", "", text)
    text = re.sub(r"<@!?\d+>", "", text)
    return re.sub(r"\s+", " ", text).strip()

async def play_next(guild_id):
    global is_speaking
    if not tts_queue:
        is_speaking = False
        return

    is_speaking = True
    vc, text = tts_queue.popleft()

    if not vc or not vc.is_connected():
        is_speaking = False
        return await play_next(guild_id)

    # Tạo file tạm trong thư mục /tmp của Linux
    filename = os.path.join(tempfile.gettempdir(), f"{uuid.uuid4().hex}.mp3")
    
    try:
        tts = gTTS(text=text, lang="vi")
        await asyncio.to_thread(tts.save, filename)

        # CẤU HÌNH FFMPEG QUAN TRỌNG NHẤT
        # Bỏ tham số executable=FFMPEG_PATH để hệ thống tự tìm trong /usr/bin/ffmpeg
        source = discord.FFmpegPCMAudio(
            filename,
            before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
            options="-vn -filter:a 'volume=1.5'"
        )

        def after_playing(error):
            if error: print(f"Lỗi phát nhạc: {error}")
            if os.path.exists(filename): os.remove(filename)
            # Gọi câu tiếp theo trong hàng đợi
            bot.loop.create_task(play_next(guild_id))

        vc.play(source, after=after_playing)

    except Exception as e:
        print(f"Lỗi TTS: {e}")
        if os.path.exists(filename): os.remove(filename)
        is_speaking = False
        await play_next(guild_id)

@bot.event
async def on_ready():
    # Không cần load_opus thủ công vì Dockerfile đã cài libopus0
    await bot.tree.sync(guild=MY_GUILD)
    print(f"Bot Online: {bot.user}")

@bot.tree.command(name="n", description="Nói văn bản", guild=MY_GUILD)
async def n(interaction: discord.Interaction, text: str):
    if not interaction.user.voice:
        return await interaction.response.send_message("Bạn chưa vào Voice!", ephemeral=True)

    await interaction.response.defer(ephemeral=True)
    
    vc = interaction.guild.voice_client
    if not vc:
        vc = await interaction.user.voice.channel.connect(self_deaf=True)
    elif vc.channel != interaction.user.voice.channel:
        await vc.move_to(interaction.user.voice.channel)

    content = clean_text(text)
    if content:
        tts_queue.append((vc, content))
        if not is_speaking:
            await play_next(interaction.guild.id)
        await interaction.followup.send(f"Đã nhận: {content[:20]}...")
    else:
        await interaction.followup.send("Nội dung trống!")

@bot.tree.command(name="out", description="Thoát voice", guild=MY_GUILD)
async def out(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc:
        await vc.disconnect()
        global is_speaking
        is_speaking = False
        tts_queue.clear()
        await interaction.response.send_message("Đã thoát!")
    else:
        await interaction.response.send_message("Bot không ở trong voice.")

async def main():
    async with bot:
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
