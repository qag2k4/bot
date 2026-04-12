import os
import asyncio
import discord
from discord.ext import commands
from gtts import gTTS
import uuid
import tempfile
from flask import Flask
from threading import Thread

# WEB SERVER GIỮ SỐNG BOT
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
intents.voice_states = True # Cần thiết để kiểm tra người dùng ở phòng nào
bot = commands.Bot(command_prefix="!", intents=intents)

speech_lock = asyncio.Lock()
AUTO_TTS = False
TTS_CHANNEL_ID = None

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Bot online: {bot.user}")

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
            if os.path.exists(filename):
                try: os.remove(filename)
                except: pass

@bot.tree.command(name="join", description="Mời bot vào phòng")
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

@bot.tree.command(name="n", description="Bot nói nội dung bạn nhập")
async def n(interaction: discord.Interaction, text: str):
    await interaction.response.send_message(f"📢: {text}", ephemeral=True)
    vc = interaction.guild.voice_client
    if vc: asyncio.create_task(play_tts(vc, text))
    else: await interaction.followup.send("❌ Bot chưa vào voice, hãy dùng /join", ephemeral=True)

@bot.tree.command(name="auto", description="Bật tự động đọc tin nhắn trong kênh này (Chỉ người cùng phòng)")
async def auto(interaction: discord.Interaction):
    global AUTO_TTS, TTS_CHANNEL_ID
    AUTO_TTS = True
    TTS_CHANNEL_ID = interaction.channel.id
    await interaction.response.send_message("🎙️ **AUTO TTS: BẬT**\n*(Chỉ đọc tin nhắn của người ở cùng phòng với bot)*", ephemeral=True)

@bot.tree.command(name="tat", description="Tắt tự động đọc tin nhắn")
async def tat(interaction: discord.Interaction):
    global AUTO_TTS
    AUTO_TTS = False
    await interaction.response.send_message("🔇 **AUTO TTS: TẮT**", ephemeral=True)

@bot.tree.command(name="out", description="Cho bot thoát")
async def out(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc:
        await vc.disconnect(force=True)
        await interaction.response.send_message("👋 Tạm biệt!", ephemeral=True)

@bot.event
async def on_message(message: discord.Message):
    # Bỏ qua nếu là bot hoặc chưa bật Auto
    if message.author.bot or not AUTO_TTS: return
    # Bỏ qua nếu không đúng kênh được chỉ định
    if TTS_CHANNEL_ID and message.channel.id != TTS_CHANNEL_ID: return
    
    vc = message.guild.voice_client
    # KIỂM TRA ĐIỀU KIỆN CÙNG PHÒNG
    if vc and vc.is_connected():
        # Nếu người chat không ở trong voice hoặc ở phòng khác với bot thì bỏ qua
        if not message.author.voice or message.author.voice.channel != vc.channel:
            return
            
        content = message.content.strip()
        if content: 
            asyncio.create_task(play_tts(vc, content))

bot.run(TOKEN)
