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
# CONFIG
# ==========================================
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1440581960069287939  # ID Server của bạn

# ==========================================
# WEB SERVER (Giữ bot sống trên Render)
# ==========================================
app = Flask(__name__)

@app.route("/")
def home(): return "Bot is alive", 200

@app.route("/healthz")
def healthz(): return "OK", 200

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
    if not guild.voice_client:
        return
    
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
            tts = gTTS(text=text, lang='vi')
            tts.save(fp.name)
            temp_path = fp.name

        source = discord.FFmpegPCMAudio(temp_path)
        guild.voice_client.play(source, after=lambda e: os.remove(temp_path))
    except Exception as e:
        print(f"Lỗi phát TTS: {e}")

# ==========================================
# MAIN BOT LOGIC
# ==========================================
def setup_bot(bot):
    tree = bot.tree
    guild_obj = discord.Object(id=GUILD_ID)

    @bot.event
    async def on_ready():
        print(f"✅ Bot Online: {bot.user}")
        try:
            # Đồng bộ lệnh vào Guild cụ thể để cập nhật ngay lập tức
            await tree.sync(guild=guild_obj)
            print("🔄 Đã đồng bộ Command Tree!")
        except Exception as e:
            print(f"❌ Sync Error: {e}")

    # --- Lệnh /join ---
    @tree.command(name="join", description="Bot vào kênh voice của bạn", guild=guild_obj)
    async def join(interaction: discord.Interaction):
        if not interaction.user.voice:
            return await interaction.response.send_message("❌ Bạn không ở trong voice!", ephemeral=True)
        
        await interaction.response.defer()
        channel = interaction.user.voice.channel
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.move_to(channel)
        else:
            await channel.connect(self_deaf=True)
        await interaction.followup.send(f"✅ Đã vào {channel.name}")

    # --- Lệnh /n (Sửa lỗi CommandNotFound của bạn) ---
    @tree.command(name="n", description="Nói nội dung bất kỳ", guild=guild_obj)
    @app_commands.describe(text="Nội dung cần nói")
    async def speak(interaction: discord.Interaction, text: str):
        if not interaction.guild.voice_client:
            return await interaction.response.send_message("❌ Bot chưa vào voice. Hãy dùng /join trước!", ephemeral=True)
        
        await interaction.response.send_message(f"🗣️ Đang nói: {text}")
        await play_tts(interaction.guild, text)

    # --- Lệnh /auto ---
    @tree.command(name="auto", description="Bật tự động đọc tin nhắn trong kênh này", guild=guild_obj)
    async def auto(interaction: discord.Interaction):
        state.AUTO_TTS = True
        state.TTS_CHANNEL_ID = interaction.channel_id
        await interaction.response.send_message(f"📢 Đã bật tự động đọc tại kênh <#{interaction.channel_id}>")

    # --- Lệnh /tat ---
    @tree.command(name="tat", description="Tắt tự động đọc", guild=guild_obj)
    async def tat(interaction: discord.Interaction):
        state.AUTO_TTS = False
        await interaction.response.send_message("📴 Đã tắt tự động đọc.")

    # --- Lệnh /out ---
    @tree.command(name="out", description="Bot rời khỏi voice", guild=guild_obj)
    async def out(interaction: discord.Interaction):
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.disconnect()
            await interaction.response.send_message("👋 Tạm biệt!")
        else:
            await interaction.response.send_message("❌ Bot có ở trong voice đâu?", ephemeral=True)

    # --- Xử lý tự động đọc tin nhắn ---
    @bot.event
    async def on_message(message):
        if message.author.bot: return
        if state.AUTO_TTS and message.channel.id == state.TTS_CHANNEL_ID:
            if message.guild.voice_client:
                await play_tts(message.guild, message.content)

def main():
    # Chạy Web server
    Thread(target=run_web, daemon=True).start()

    while True:
        intents = discord.Intents.default()
        intents.message_content = True
        bot = commands.Bot(command_prefix="!", intents=intents)
        
        setup_bot(bot)

        try:
            print("🚀 Đang khởi động Bot...")
            bot.run(TOKEN)
        except discord.errors.HTTPException as e:
            if e.status == 429:
                print("🔥 LỖI 429: Discord chặn IP. Đang khởi động lại để đổi IP...")
                time.sleep(5)
                sys.exit(1) # Render sẽ tự restart app
            else:
                print(f"Lỗi HTTP: {e}")
                time.sleep(10)
        except Exception as e:
            print(f"Lỗi hệ thống: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
