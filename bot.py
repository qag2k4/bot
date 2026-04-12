import os
import asyncio
import discord
from discord.ext import commands
from gtts import gTTS
import uuid
import tempfile
from flask import Flask
from threading import Thread

# ==========================================
# WEB SERVER (Giữ bot sống trên Render)
# ==========================================
app = Flask('')

@app.route('/')
def home(): return "Bot is alive"

@app.route('/healthz')
def healthz(): return "OK"

def run():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

Thread(target=run, daemon=True).start()

# ==========================================
# CẤU HÌNH BOT DISCORD
# ==========================================
TOKEN = os.getenv("DISCORD_TOKEN")
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True 

bot = commands.Bot(command_prefix="!", intents=intents)

# Biến điều khiển
speech_lock = asyncio.Lock()
AUTO_TTS = False
TTS_CHANNEL_ID = None

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Bot online: {bot.user}")

async def play_tts(vc, text):
    async with speech_lock:
        filename = os.path.join(tempfile.gettempdir(), f"{uuid.uuid4()}.mp3")
        try:
            tts = gTTS(text=text, lang='vi')
            await asyncio.to_thread(tts.save, filename)
            if not vc or not vc.is_connected(): return
            source = discord.FFmpegPCMAudio(filename, options="-vn")
            def after_playing(e):
                if os.path.exists(filename):
                    try: os.remove(filename)
                    except: pass
            vc.play(source, after=after_playing)
            while vc.is_playing(): await asyncio.sleep(0.2)
        except Exception:
            if os.path.exists(filename): os.remove(filename)

# ==========================================
# LOGIC TỰ ĐỘNG THOÁT KHI PHÒNG TRỐNG (Đợi 1 phút)
# ==========================================
@bot.event
async def on_voice_state_update(member, before, after):
    voice_client = member.guild.voice_client
    if not voice_client:
        return

    # Nếu có người rời phòng hoặc chuyển phòng
    if before.channel is not None and before.channel == voice_client.channel:
        # Đếm số lượng người thật (không phải bot)
        non_bot_members = [m for m in voice_client.channel.members if not m.bot]
        
        if len(non_bot_members) == 0:
            print(f"Phòng trống. Bot sẽ chờ 1 phút trước khi rời đi...")
            # Đợi 60 giây
            await asyncio.sleep(60)
            
            # Kiểm tra lại một lần nữa sau 60 giây
            if voice_client.is_connected():
                non_bot_members = [m for m in voice_client.channel.members if not m.bot]
                if len(non_bot_members) == 0:
                    await voice_client.disconnect(force=True)
                    print(f"Bot đã tự động rời phòng {before.channel.name} sau 1 phút chờ.")

# ==========================================
# CÁC LỆNH SLASH (/) 
# ==========================================

@bot.tree.command(name="join", description="Mời bot vào phòng Voice")
async def join(interaction: discord.Interaction):
    if not interaction.user.voice:
        return await interaction.response.send_message("❌ Bạn chưa vào Voice!", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    try:
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.move_to(interaction.user.voice.channel)
        else:
            await interaction.user.voice.channel.connect(timeout=20.0, self_deaf=True)
        await interaction.followup.send(f"✅ Đã kết nối!")
    except Exception as e:
        await interaction.followup.send(f"Lỗi: {e}")

@bot.tree.command(name="n", description="Bot nói nội dung (Riêng tư)")
async def n(interaction: discord.Interaction, text: str):
    await interaction.response.send_message(f"📢: {text}", ephemeral=True)
    vc = interaction.guild.voice_client
    if vc: asyncio.create_task(play_tts(vc, text))
    else: await interaction.followup.send("❌ Bot chưa vào voice, hãy dùng /join", ephemeral=True)

@bot.tree.command(name="auto", description="Bật tự động đọc tin nhắn (Chỉ người cùng phòng)")
async def auto(interaction: discord.Interaction):
    global AUTO_TTS, TTS_CHANNEL_ID
    AUTO_TTS = True
    TTS_CHANNEL_ID = interaction.channel.id
    await interaction.response.send_message("🎙️ **AUTO TTS: BẬT**\n*(Chỉ đọc tin nhắn của người ở cùng phòng voice)*", ephemeral=True)

@bot.tree.command(name="tat", description="Tắt chế độ tự động đọc")
async def tat(interaction: discord.Interaction):
    global AUTO_TTS
    AUTO_TTS = False
    await interaction.response.send_message("🔇 **AUTO TTS: TẮT**", ephemeral=True)

@bot.tree.command(name="out", description="Mời bot rời khỏi Voice")
async def out(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc:
        await vc.disconnect(force=True)
        await interaction.response.send_message("👋 Tạm biệt!", ephemeral=True)
    else:
        await interaction.response.send_message("Bot không ở trong phòng nào.", ephemeral=True)

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not AUTO_TTS: return
    if TTS_CHANNEL_ID and message.channel.id != TTS_CHANNEL_ID: return
    vc = message.guild.voice_client
    if vc and vc.is_connected():
        if not message.author.voice or message.author.voice.channel != vc.channel: return
        content = message.content.strip()
        if content: asyncio.create_task(play_tts(vc, content))

bot.run(TOKEN)
