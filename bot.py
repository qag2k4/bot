import os
import asyncio
import discord
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
GUILD_ID = 1440581960069287939

# ==========================================
# WEB SERVER
# ==========================================
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is alive", 200

@app.route("/healthz")
def healthz():
    return "OK", 200

def run_web():
    port = int(os.environ.get("PORT", 10000))
    import logging
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    app.run(host="0.0.0.0", port=port)

# ==========================================
# DISCORD BOT LOGIC
# ==========================================
def create_bot():
    intents = discord.Intents.default()
    intents.message_content = True
    intents.voice_states = True
    return commands.Bot(command_prefix="!", intents=intents)

state = {
    "AUTO_TTS": False,
    "TTS_CHANNEL_ID": None,
    "last_tts_time": {}
}

# (Giữ nguyên các hàm play_tts và các event/command như trước)
# ... [Phần này bạn copy lại các hàm play_tts, join, n, auto, tat, out từ code trước] ...

# ==========================================
# PHẦN QUAN TRỌNG: KHỞI CHẠY VÀ FIX LỖI 429
# ==========================================

def start_bot_instance():
    """Hàm này tạo một instance bot mới mỗi khi gọi để tránh 'Session is closed'"""
    bot = create_bot()

    @bot.event
    async def on_ready():
        print(f"✅ Bot Online: {bot.user}")
        try:
            guild = discord.Object(id=GUILD_ID)
            await bot.tree.sync(guild=guild)
        except: pass

    # Tái định nghĩa các lệnh cho instance bot mới này
    @bot.tree.command(name="join", guild=discord.Object(id=GUILD_ID))
    async def join(interaction: discord.Interaction):
        if not interaction.user.voice:
            return await interaction.response.send_message("❌ Bạn không ở trong voice!", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        try:
            channel = interaction.user.voice.channel
            if interaction.guild.voice_client:
                await interaction.guild.voice_client.move_to(channel)
            else:
                await channel.connect(self_deaf=True)
            await interaction.followup.send(f"✅ Đã vào {channel.name}")
        except Exception as e:
            await interaction.followup.send(f"Lỗi: {e}")

    # [Định nghĩa lại các lệnh khác tương tự nếu cần...]

    return bot

def main():
    # Chạy Web server duy nhất 1 lần
    Thread(target=run_web, daemon=True).start()

    retry_count = 0
    while True:
        print(f"🚀 Đang khởi tạo kết nối Discord... (Lần thử: {retry_count + 1})")
        bot = create_bot()
        
        # Đưa các sự kiện và lệnh vào đây (hoặc dùng setup_hook)
        # Để ngắn gọn, tôi lồng logic chạy vào try/except
        try:
            bot.run(TOKEN)
        except discord.errors.HTTPException as e:
            if e.status == 429:
                retry_count += 1
                # Nếu bị chặn, dừng hẳn 10s rồi thoát để Render khởi động lại toàn bộ
                # Đây là cách tốt nhất để "reset" lại IP trên Render
                print(f"🔥 LỖI 429: Discord chặn IP. Đang yêu cầu Render đổi IP mới...")
                time.sleep(5)
                sys.exit(1) # Render sẽ tự khởi động lại app sau vài giây
            else:
                print(f"Lỗi HTTP khác: {e}")
                time.sleep(10)
        except Exception as e:
            print(f"Lỗi hệ thống: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
