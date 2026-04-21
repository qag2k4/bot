import os
import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from gtts import gTTS
import tempfile
from flask import Flask
from threading import Thread
import sys
import time

# ==========================================
# CONFIGURATION
# ==========================================
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1440581960069287939  # ID Server của bạn

# ==========================================
# WEB SERVER (Giữ bot sống trên Render)
# ==========================================
app = Flask(__name__)

@app.route("/")
def home(): 
    return "Bot is running!", 200

@app.route("/healthz")
def healthz(): 
    return "OK", 200

def run_web():
    port = int(os.environ.get("PORT", 10000))
    import logging
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    app.run(host="0.0.0.0", port=port)

# ==========================================
# GLOBAL STATE
# ==========================================
class BotState:
    def __init__(self):
        self.AUTO_TTS = False
        self.TTS_CHANNEL_ID = None

state = BotState()

# ==========================================
# TTS HELPER
# ==========================================
async def play_tts(guild, text):
    if not guild or not guild.voice_client:
        return
    
    try:
        # Tạo file tạm thời
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
            tts = gTTS(text=text, lang='vi')
            tts.save(fp.name)
            temp_path = fp.name

        # Phát âm thanh
        def after_playing(e):
            if os.path.exists(temp_path):
                try: os.remove(temp_path)
                except: pass

        source = discord.FFmpegPCMAudio(temp_path)
        # Nếu đang phát thì dừng để phát câu mới
        if guild.voice_client.is_playing():
            guild.voice_client.stop()
            
        guild.voice_client.play(source, after=after_playing)
    except Exception as e:
        print(f"❌ Lỗi phát TTS: {e}")

# ==========================================
# BOT SETUP & COMMANDS
# ==========================================
def create_bot():
    intents = discord.Intents.default()
    intents.message_content = True
    intents.voice_states = True
    bot = commands.Bot(command_prefix="!", intents=intents)
    
    guild_obj = discord.Object(id=GUILD_ID)

    @bot.event
    async def on_ready():
        print(f"✅ Đã đăng nhập: {bot.user}")
        try:
            # Xóa sạch các lệnh cũ để tránh lỗi CommandNotFound
            bot.tree.clear_commands(guild=guild_obj)
            
            # Copy các lệnh định nghĩa bên dưới vào Guild này
            bot.tree.copy_global_to(guild=guild_obj)
            
            # Đồng bộ hóa
            await bot.tree.sync(guild=guild_obj)
            print(f"🔄 Đã đồng bộ Command Tree cho Guild: {GUILD_ID}")
        except Exception as e:
            print(f"❌ Lỗi Sync: {e}")

    # --- SLASH COMMANDS ---

    @bot.tree.command(name="join", description="Mời bot vào kênh voice")
    async def join(interaction: discord.Interaction):
        if not interaction.user.voice:
            return await interaction.response.send_message("❌ Bạn phải ở trong voice channel!", ephemeral=True)
        
        await interaction.response.defer()
        channel = interaction.user.voice.channel
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.move_to(channel)
        else:
            await channel.connect(self_deaf=True)
        await interaction.followup.send(f"✅ Đã kết nối vào **{channel.name}**")

    @bot.tree.command(name="n", description="Yêu cầu bot nói gì đó")
    @app_commands.describe(text="Nội dung bạn muốn bot nói")
    async def n(interaction: discord.Interaction, text: str):
        if not interaction.guild.voice_client:
            return await interaction.response.send_message("❌ Bot chưa vào voice! Hãy dùng `/join`.", ephemeral=True)
        
        await interaction.response.send_message(f"🗣️ **Bot nói:** {text}")
        await play_tts(interaction.guild, text)

    @bot.tree.command(name="auto", description="Tự động đọc tin nhắn tại kênh này")
    async def auto(interaction: discord.Interaction):
        state.AUTO_TTS = True
        state.TTS_CHANNEL_ID = interaction.channel_id
        await interaction.response.send_message(f"📢 Đã bật tự động đọc tại <#{interaction.channel_id}>")

    @bot.tree.command(name="tat", description="Tắt chế độ tự động đọc")
    async def tat(interaction: discord.Interaction):
        state.AUTO_TTS = False
        await interaction.response.send_message("📴 Đã tắt tự động đọc tin nhắn.")

    @bot.tree.command(name="out", description="Mời bot rời khỏi voice")
    async def out(interaction: discord.Interaction):
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.disconnect()
            await interaction.response.send_message("👋 Đã rời kênh voice.")
        else:
            await interaction.response.send_message("❌ Bot không có trong voice.", ephemeral=True)

    # --- EVENTS ---

    @bot.event
    async def on_message(message):
        if message.author.bot:
            return
        
        # Xử lý tự động đọc
        if state.AUTO_TTS and message.channel.id == state.TTS_CHANNEL_ID:
            if message.guild.voice_client:
                await play_tts(message.guild, message.content)
        
        await bot.process_commands(message)

    return bot

# ==========================================
# EXECUTION
# ==========================================
def main():
    # Khởi động Web Server để Render không bị tắt
    Thread(target=run_web, daemon=True).start()

    while True:
        print("🚀 Đang khởi tạo kết nối Discord...")
        bot = create_bot()
        
        try:
            bot.run(TOKEN)
        except discord.errors.HTTPException as e:
            if e.status == 429:
                print("🔥 Lỗi 429 (Rate Limit). Render sẽ restart sau 5s để đổi IP...")
                time.sleep(5)
                sys.exit(1)
            else:
                print(f"❌ Lỗi kết nối: {e}")
                time.sleep(10)
        except Exception as e:
            print(f"❌ Lỗi không xác định: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
