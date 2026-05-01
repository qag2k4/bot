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
import re

# ==========================================
# CONFIGURATION
# ==========================================
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1440581960069287939 

# ==========================================
# WEB SERVER
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
# CLEAN TEXT HELPER
# ==========================================
def clean_tts_text(text: str) -> str:
    # Xóa link
    text = re.sub(r'https?://\S+|www\.\S+', '', text)

    # Xóa mention, channel, custom emoji Discord: <@id>, <#id>, <:emoji:id>
    text = re.sub(r'<[^>]+>', '', text)

    # Xóa emoji/icon unicode
    text = re.sub(
        r'[\U0001F300-\U0001FAFF\U00002700-\U000027BF\U00002600-\U000026FF]',
        '',
        text
    )

    # Gọn khoảng trắng
    text = re.sub(r'\s+', ' ', text).strip()

    return text

# ==========================================
# TTS HELPER
# ==========================================
async def play_tts(guild, text):
    if not guild or not guild.voice_client:
        return

    text = clean_tts_text(text)
    if not text:
        return
    
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
            tts = gTTS(text=text, lang='vi')
            tts.save(fp.name)
            temp_path = fp.name

        def after_playing(e):
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass

        source = discord.FFmpegPCMAudio(temp_path)

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
            bot.tree.clear_commands(guild=guild_obj)
            bot.tree.copy_global_to(guild=guild_obj)
            await bot.tree.sync(guild=guild_obj)
            print(f"🔄 Đã đồng bộ Command Tree!")
        except Exception as e:
            print(f"❌ Lỗi Sync: {e}")

    # --- Lệnh /join ---
    @bot.tree.command(name="join", description="Mời bot vào kênh voice")
    async def join(interaction: discord.Interaction):
        if not interaction.user.voice:
            return await interaction.response.send_message(
                "❌ Bạn phải ở trong voice channel!",
                ephemeral=True
            )
        
        await interaction.response.defer(ephemeral=True)

        channel = interaction.user.voice.channel

        if interaction.guild.voice_client:
            await interaction.guild.voice_client.move_to(channel)
        else:
            await channel.connect(self_deaf=True)

        await interaction.followup.send(f"✅ Đã kết nối vào **{channel.name}**")

    # --- Lệnh /n ---
    @bot.tree.command(name="n", description="Yêu cầu bot nói (Chỉ bạn thấy tin nhắn này)")
    @app_commands.describe(text="Nội dung bạn muốn bot nói")
    async def n(interaction: discord.Interaction, text: str):
        if not interaction.user.voice:
            return await interaction.response.send_message(
                "❌ Bạn cần vào một kênh voice trước!",
                ephemeral=True
            )

        cleaned_text = clean_tts_text(text)

        if not cleaned_text:
            return await interaction.response.send_message(
                "⚠️ Nội dung chỉ có link/icon nên bot không đọc.",
                ephemeral=True
            )

        await interaction.response.send_message(
            f"🗣️ Đang đọc: {cleaned_text}",
            ephemeral=True
        )

        user_channel = interaction.user.voice.channel

        if not interaction.guild.voice_client:
            await user_channel.connect(self_deaf=True)
        elif interaction.guild.voice_client.channel != user_channel:
            await interaction.guild.voice_client.move_to(user_channel)

        await play_tts(interaction.guild, cleaned_text)

    # --- Lệnh /auto ---
    @bot.tree.command(name="auto", description="Tự động đọc tin nhắn tại kênh này")
    async def auto(interaction: discord.Interaction):
        state.AUTO_TTS = True
        state.TTS_CHANNEL_ID = interaction.channel_id

        await interaction.response.send_message(
            f"📢 Đã bật tự động đọc tại <#{interaction.channel_id}>",
            ephemeral=True
        )

    # --- Lệnh /tat ---
    @bot.tree.command(name="tat", description="Tắt chế độ tự động đọc")
    async def tat(interaction: discord.Interaction):
        state.AUTO_TTS = False

        await interaction.response.send_message(
            "📴 Đã tắt tự động đọc.",
            ephemeral=True
        )

    # --- Lệnh /out ---
    @bot.tree.command(name="out", description="Mời bot rời khỏi voice")
    async def out(interaction: discord.Interaction):
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.disconnect()
            await interaction.response.send_message(
                "👋 Đã rời kênh voice.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "⚠️ Bot chưa ở trong voice.",
                ephemeral=True
            )

    # --- Auto đọc tin nhắn ---
    @bot.event
    async def on_message(message):
        if message.author.bot:
            return

        if state.AUTO_TTS and message.channel.id == state.TTS_CHANNEL_ID:
            if message.guild.voice_client:
                cleaned_text = clean_tts_text(message.content)
                if cleaned_text:
                    await play_tts(message.guild, cleaned_text)

        await bot.process_commands(message)

    return bot

# ==========================================
# MAIN
# ==========================================
def main():
    Thread(target=run_web, daemon=True).start()

    while True:
        bot = create_bot()

        try:
            bot.run(TOKEN)

        except discord.errors.HTTPException as e:
            if e.status == 429:
                print("❌ Bị Discord rate limit 429. Dừng bot để Render tự restart.")
                time.sleep(5)
                sys.exit(1)
            else:
                print(f"❌ Discord HTTPException: {e}")
                time.sleep(10)

        except Exception as e:
            print(f"❌ Lỗi bot: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
