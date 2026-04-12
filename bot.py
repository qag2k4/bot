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
# WEB SERVER (Dành cho Render/Koyeb)
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

async def generate_tts_file(text: str, filename: str):
    def _save():
        tts = gTTS(text=text, lang="vi")
        tts.save(filename)
    await asyncio.to_thread(_save)

def add_to_queue(vc: discord.VoiceClient, text: str):
    text = clean_text(text)
    if not text:
        return
    tts_queue.append((vc, text))
    # Chạy play_next nếu chưa có luồng nào đang chạy
    if not is_speaking:
        asyncio.create_task(play_next())

async def play_next():
    global is_speaking
    if is_speaking or not tts_queue:
        return

    is_speaking = True
    
    try:
        while tts_queue:
            vc, text = tts_queue.popleft()

            if not vc or not vc.is_connected():
                continue

            filename = os.path.join(tempfile.gettempdir(), f"tts_{uuid.uuid4().hex}.mp3")

            try:
                await asyncio.wait_for(generate_tts_file(text, filename), timeout=15)
                
                if not vc.is_connected():
                    if os.path.exists(filename): os.remove(filename)
                    continue

                finished = asyncio.Event()

                def after_play(err):
                    if err:
                        print(f"FFmpeg error: {err}")
                    if os.path.exists(filename):
                        try: os.remove(filename)
                        except: pass
                    bot.loop.call_soon_threadsafe(finished.set)

                # Cấu hình FFmpeg tối ưu cho stream
                source = discord.FFmpegPCMAudio(
                    filename,
                    options="-vn -b:a 128k"
                )
                
                vc.play(source, after=after_play)
                await finished.wait()

            except Exception as e:
                print(f"Lỗi trong khi phát TTS: {e}")
                if os.path.exists(filename):
                    try: os.remove(filename)
                    except: pass
    finally:
        is_speaking = False

# ==========================================
# EVENTS
# ==========================================
@bot.event
async def on_ready():
    # Thử load opus nếu môi trường yêu cầu (thường Docker Linux cần)
    if not discord.opus.is_loaded():
        for lib in ['libopus.so.0', 'libopus.so', 'opus']:
            try:
                discord.opus.load_opus(lib)
                print(f"Opus loaded using {lib}")
                break
            except:
                continue
    
    try:
        synced = await bot.tree.sync(guild=MY_GUILD)
        print(f"Bot online: {bot.user} | Đã sync {len(synced)} lệnh.")
    except Exception as e:
        print(f"Sync error: {e}")

@bot.event
async def on_voice_state_update(member, before, after):
    if member.id == bot.user.id and before.channel and not after.channel:
        global is_speaking, tts_queue
        tts_queue.clear()
        is_speaking = False

# ==========================================
# SLASH COMMANDS
# ==========================================
@bot.tree.command(name="join", description="Gọi bot vào phòng voice", guild=MY_GUILD)
async def join(interaction: discord.Interaction):
    if not interaction.user.voice:
        return await interaction.response.send_message("Vào voice đi rồi gọi!", ephemeral=True)
    
    await interaction.response.defer(ephemeral=True)
    channel = interaction.user.voice.channel
    try:
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.move_to(channel)
        else:
            await channel.connect(self_deaf=True)
        await interaction.followup.send(f"Đã vào {channel.name}")
    except Exception as e:
        await interaction.followup.send(f"Lỗi: {e}")

@bot.tree.command(name="n", description="Bot nói nội dung bạn nhập", guild=MY_GUILD)
async def n(interaction: discord.Interaction, text: str):
    if not interaction.user.voice:
        return await interaction.response.send_message("Bạn phải ở trong Voice!", ephemeral=True)

    await interaction.response.defer(ephemeral=True)
    
    guild = interaction.guild
    vc = guild.voice_client

    if not vc:
        vc = await interaction.user.voice.channel.connect(self_deaf=True)
    elif vc.channel != interaction.user.voice.channel:
        await vc.move_to(interaction.user.voice.channel)

    add_to_queue(vc, text)
    await interaction.followup.send(f"Đã thêm vào hàng đợi: {text[:20]}...")

@bot.tree.command(name="out", description="Thoát voice", guild=MY_GUILD)
async def out(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc:
        await vc.disconnect()
        await interaction.response.send_message("Tạm biệt!")
    else:
        await interaction.response.send_message("Bot có ở trong phòng nào đâu?")

@bot.tree.command(name="skip", description="Bỏ qua câu hiện tại", guild=MY_GUILD)
async def skip(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.stop()
        await interaction.response.send_message("Đã skip!")
    else:
        await interaction.response.send_message("Đang không nói gì cả.")

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not AUTO_TTS: return
    vc = message.guild.voice_client
    if vc and message.author.voice and message.author.voice.channel == vc.channel:
        add_to_queue(vc, message.content)

async def main():
    async with bot:
        await bot.start(TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
