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
def home(): 
    return "Bot is alive"

@app.route('/healthz')
def healthz(): 
    return "OK"

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
    # Sync Global: Giúp bot dùng được trên nhiều Server khác nhau
    print("Đang đồng bộ lệnh toàn cầu...")
    await bot.tree.sync()
    print(f"✅ Bot online: {bot.user}")

async def play_tts(vc, text):
    """Xử lý tạo file âm thanh và phát vào Voice Channel"""
    async with speech_lock:
        filename = os.path.join(tempfile.gettempdir(), f"{uuid.uuid4()}.mp3")
        try:
            # Chuyển văn bản thành gTTS
            tts = gTTS(text=text, lang='vi')
            await asyncio.to_thread(tts.save, filename)
            
            if not vc or not vc.is_connected():
                return

            # Cấu hình FFmpeg tối ưu cho môi trường Docker/Render
            source = discord.FFmpegPCMAudio(filename, options="-vn")
            
            def after_playing(e):
                if os.path.exists(filename):
                    try: os.remove(filename)
                    except: pass

            vc.play(source, after=after_playing)
            
            # Đợi nói xong mới mở khóa cho câu tiếp theo
            while vc.is_playing():
                await asyncio.sleep(0.2)
                
        except Exception as e:
            print(f"Lỗi phát âm thanh: {e}")
            if os.path.exists(filename):
                try: os.remove(filename)
                except: pass

# ==========================================
# CÁC LỆNH SLASH (/) 
# ==========================================

@bot.tree.command(name="join", description="Mời bot vào phòng Voice")
async def join(interaction: discord.Interaction):
    if not interaction.user.voice:
        return await interaction.response.send_message("❌ Bạn chưa vào Voice!", ephemeral=True)
    
    await interaction.response.defer(ephemeral=True)
    channel = interaction.user.voice.channel
    try:
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.move_to(channel)
        else:
            await channel.connect(timeout=20.0, self_deaf=True)
        await interaction.followup.send(f"✅ Đã kết nối vào **{channel.name}**")
    except Exception as e:
        await interaction.followup.send(f"Lỗi kết nối: {e}")

@bot.tree.command(name="n", description="Bot nói nội dung bạn nhập (Riêng tư)")
async def n(interaction: discord.Interaction, text: str):
    # Phản hồi riêng tư để không rác kênh chat
    await interaction.response.send_message(f"📢 Đang nói: {text}", ephemeral=True)

    if not interaction.user.voice:
        return await interaction.followup.send("❌ Bạn cần vào Voice trước!", ephemeral=True)

    vc = interaction.guild.voice_client
    try:
        if not vc:
            vc = await interaction.user.voice.channel.connect(timeout=20.0, self_deaf=True)
        elif vc.channel != interaction.user.voice.channel:
            await vc.move_to(interaction.user.voice.channel)
        
        asyncio.create_task(play_tts(vc, text))
    except Exception as e:
        print(f"Voice Error: {e}")
        if vc: await vc.disconnect(force=True)

@bot.tree.command(name="auto", description="Bật tự động đọc tin nhắn (Chỉ người cùng phòng)")
async def auto(interaction: discord.Interaction):
    global AUTO_TTS, TTS_CHANNEL_ID
    AUTO_TTS = True
    TTS_CHANNEL_ID = interaction.channel.id
    await interaction.response.send_message("🎙️ **AUTO TTS: BẬT**\n*(Bot chỉ đọc tin nhắn của người ở cùng phòng Voice)*", ephemeral=True)

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

# ==========================================
# XỬ LÝ TỰ ĐỘNG ĐỌC TIN NHẮN
# ==========================================
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not AUTO_TTS: 
        return
    if TTS_CHANNEL_ID and message.channel.id != TTS_CHANNEL_ID: 
        return
    
    vc = message.guild.voice_client
    if vc and vc.is_connected():
        # Chỉ đọc nếu người chat ở cùng phòng voice với bot
        if not message.author.voice or message.author.voice.channel != vc.channel:
            return
            
        content = message.content.strip()
        if content: 
            asyncio.create_task(play_tts(vc, content))

# Chạy Bot
bot.run(TOKEN)
