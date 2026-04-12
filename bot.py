import os
import asyncio
import discord
from discord.ext import commands
from gtts import gTTS
import uuid
import tempfile
from flask import Flask
from threading import Thread

# WEB SERVER
app = Flask('')
@app.route('/')
def home(): return "Bot is alive"
@app.route('/healthz')
def healthz(): return "OK"
def run(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))
Thread(target=run, daemon=True).start()

# CẤU HÌNH BOT
TOKEN = os.getenv("DISCORD_TOKEN")
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Bot logged in as {bot.user}")

async def speak_text(vc, text):
    if not vc or not vc.is_connected():
        return
        
    filename = os.path.join(tempfile.gettempdir(), f"{uuid.uuid4()}.mp3")
    try:
        tts = gTTS(text=text, lang='vi')
        await asyncio.to_thread(tts.save, filename)
        
        # Đảm bảo bot vẫn còn kết nối trước khi play
        if not vc.is_connected(): return

        source = discord.FFmpegPCMAudio(filename, options="-vn")
        
        # Sử dụng loop.call_soon_threadsafe để dọn dẹp file tránh treo ffmpeg
        def after_playing(e):
            if os.path.exists(filename):
                try: os.remove(filename)
                except: pass

        vc.play(source, after=after_playing)
        
        # Chờ cho đến khi nói xong
        while vc.is_playing():
            await asyncio.sleep(0.5)
            
    except Exception as e:
        print(f"Lỗi phát âm thanh: {e}")
        if os.path.exists(filename):
            try: os.remove(filename)
            except: pass

@bot.tree.command(name="n", description="Nói văn bản")
async def n(interaction: discord.Interaction, text: str):
    # 1. PHẢN HỒI NGAY LẬP TỨC để tránh lỗi 10062 (Unknown Interaction)
    await interaction.response.send_message(f"Đang chuẩn bị nói: {text[:20]}...", ephemeral=True)

    if not interaction.user.voice:
        return await interaction.followup.send("Vào voice trước đã!", ephemeral=True)

    channel = interaction.user.voice.channel
    vc = interaction.guild.voice_client

    try:
        # 2. Kết nối với timeout dài hơn và xử lý cẩn thận
        if not vc:
            vc = await channel.connect(timeout=30.0, self_deaf=True)
        elif vc.channel != channel:
            await vc.move_to(channel)
        
        # 3. Chạy hàm nói mà không làm block luồng chính
        asyncio.create_task(speak_text(vc, text))
        
    except Exception as e:
        print(f"Lỗi kết nối voice: {e}")
        if vc: await vc.disconnect(force=True)

@bot.tree.command(name="out", description="Thoát voice")
async def out(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc:
        await vc.disconnect(force=True)
        await interaction.response.send_message("Đã thoát!")
    else:
        await interaction.response.send_message("Bot không trong voice.")

bot.run(TOKEN)
