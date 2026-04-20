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
# CẤU HÌNH BOT
# ==========================================
TOKEN = os.getenv("DISCORD_TOKEN")
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True 
bot = commands.Bot(command_prefix="!", intents=intents)

speech_lock = asyncio.Lock()
AUTO_TTS = False
TTS_CHANNEL_ID = None

@bot.event
async def on_ready():
    await bot.tree.sync() # Đồng bộ lệnh toàn cầu
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

# LOGIC: Chỉ thoát khi phòng trống (sau 1 phút)
@bot.event
async def on_voice_state_update(member, before, after):
    vc = member.guild.voice_client
    if not vc: return
    if before.channel is not None and before.channel == vc.channel:
        non_bot_members = [m for m in vc.channel.members if not m.bot]
        if len(non_bot_members) == 0:
            await asyncio.sleep(60) # Chờ 1 phút
            non_bot_members = [m for m in vc.channel.members if not m.bot]
            if len(non_bot_members) == 0:
                await vc.disconnect(force=True)

# ==========================================
# LỆNH SLASH (/)
# ==========================================

@bot.tree.command(name="join", description="Mời bot vào phòng Voice")
async def join(interaction: discord.Interaction):
    if not interaction.user.voice:
        return await interaction.response.send_message("❌ Bạn chưa vào Voice!", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    try:
        channel = interaction.user.voice.channel
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.move_to(channel)
        else:
            await channel.connect(timeout=20.0, self_deaf=True)
        await interaction.followup.send(f"✅ Đã vào phòng!")
    except Exception as e:
        await interaction.followup.send(f"Lỗi: {e}")

@bot.tree.command(name="n", description="Nói và tự vào phòng nếu cần")
async def n(interaction: discord.Interaction, text: str):
    await interaction.response.send_message(f"📢: {text}", ephemeral=True)
    if not interaction.user.voice:
        return await interaction.followup.send("❌ Bạn chưa vào Voice!", ephemeral=True)

    vc = interaction.guild.voice_client
    try:
        if not vc:
            vc = await interaction.user.voice.channel.connect(timeout=20.0, self_deaf=True)
        elif vc.channel != interaction.user.voice.channel:
            await vc.move_to(interaction.user.voice.channel)
        
        asyncio.create_task(play_tts(vc, text))
    except Exception as e:
        if vc: await vc.disconnect(force=True)

@bot.tree.command(name="auto", description="Bật tự đọc (Cùng phòng)")
async def auto(interaction: discord.Interaction):
    global AUTO_TTS, TTS_CHANNEL_ID
    AUTO_TTS = True
    TTS_CHANNEL_ID = interaction.channel.id
    await interaction.response.send_message("🎙️ **AUTO: BẬT**", ephemeral=True)

@bot.tree.command(name="tat", description="Tắt tự đọc")
async def tat(interaction: discord.Interaction):
    global AUTO_TTS
    AUTO_TTS = False
    await interaction.response.send_message("🔇 **AUTO: TẮT**", ephemeral=True)

@bot.tree.command(name="out", description="Thoát Voice ngay lập tức")
async def out(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc:
        await vc.disconnect(force=True)
        await interaction.response.send_message("👋 Bye!", ephemeral=True)
    else:
        await interaction.response.send_message("Bot đang không ở trong phòng nào.", ephemeral=True)

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not AUTO_TTS: return
    if TTS_CHANNEL_ID and message.channel.id != TTS_CHANNEL_ID: return
    vc = message.guild.voice_client
    if vc and vc.is_connected() and message.author.voice and message.author.voice.channel == vc.channel:
        content = message.content.strip()
        if content: asyncio.create_task(play_tts(vc, content))

bot.run(TOKEN)
