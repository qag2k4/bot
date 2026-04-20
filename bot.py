import os
import asyncio
import discord
from discord.ext import commands
from gtts import gTTS
import tempfile
from flask import Flask
from threading import Thread
import sys

# ==========================================
# CONFIG
# ==========================================
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1440581960069287939

# ==========================================
# WEB SERVER (Giữ cho Render không ngủ)
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
    # Giảm tải log cho Render
    import logging
    logging.getLogger('werkzeug').setLevel(logging.ERROR)
    app.run(host="0.0.0.0", port=port)

# ==========================================
# DISCORD BOT - Tối ưu kết nối
# ==========================================
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

# Tăng cường khả năng kết nối lại khi gặp lỗi mạng
bot = commands.Bot(
    command_prefix="!", 
    intents=intents,
    heartbeat_timeout=60.0,
    guild_ready_timeout=20.0
)

# Trạng thái toàn cục
state = {
    "AUTO_TTS": False,
    "TTS_CHANNEL_ID": None,
    "last_tts_time": {}
}

# ==========================================
# XỬ LÝ VOICE & TTS
# ==========================================
async def play_tts(vc, text):
    if not vc or not vc.is_connected():
        return

    # Tạo file tạm an toàn
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
        filename = fp.name

    try:
        if len(text) > 200: text = text[:200]
        
        tts = gTTS(text=text, lang='vi')
        await asyncio.to_thread(tts.save, filename)

        # Chống chồng chéo âm thanh
        while vc.is_playing():
            await asyncio.sleep(0.1)

        source = discord.FFmpegPCMAudio(filename)
        
        def cleanup(error):
            if os.path.exists(filename):
                try: os.remove(filename)
                except: pass
        
        vc.play(source, after=cleanup)
    except Exception as e:
        print(f"Lỗi phát nhạc: {e}")
        if os.path.exists(filename): os.remove(filename)

# ==========================================
# EVENTS
# ==========================================
@bot.event
async def on_ready():
    print(f"✅ Đã đăng nhập: {bot.user}")
    try:
        guild = discord.Object(id=GUILD_ID)
        synced = await bot.tree.sync(guild=guild)
        print(f"⚡ Đã đồng bộ {len(synced)} lệnh Slash")
    except Exception as e:
        print(f"Lỗi sync: {e}")

@bot.event
async def on_message(message):
    if message.author.bot or not state["AUTO_TTS"]: return
    if state["TTS_CHANNEL_ID"] and message.channel.id != state["TTS_CHANNEL_ID"]: return
    
    vc = message.guild.voice_client
    if vc and vc.is_connected() and message.author.voice and message.author.voice.channel.id == vc.channel.id:
        # Chống spam nhẹ (1 giây mỗi câu)
        now = asyncio.get_event_loop().time()
        if now - state["last_tts_time"].get(message.author.id, 0) < 1: return
        state["last_tts_time"][message.author.id] = now
        
        await play_tts(vc, message.content)

# ==========================================
# SLASH COMMANDS
# ==========================================
@bot.tree.command(name="join", guild=discord.Object(id=GUILD_ID))
async def join(interaction: discord.Interaction):
    if not interaction.user.voice:
        return await interaction.response.send_message("❌ Bạn không ở trong voice!", ephemeral=True)
    
    await interaction.response.defer(ephemeral=True)
    channel = interaction.user.voice.channel
    try:
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.move_to(channel)
        else:
            await channel.connect(self_deaf=True)
        await interaction.followup.send(f"✅ Đã vào {channel.name}")
    except Exception as e:
        await interaction.followup.send(f"Lỗi kết nối: {e}")

@bot.tree.command(name="auto", guild=discord.Object(id=GUILD_ID))
async def auto(interaction: discord.Interaction):
    state["AUTO_TTS"] = True
    state["TTS_CHANNEL_ID"] = interaction.channel.id
    await interaction.response.send_message("🎙️ Auto TTS: BẬT", ephemeral=True)

@bot.tree.command(name="tat", guild=discord.Object(id=GUILD_ID))
async def tat(interaction: discord.Interaction):
    state["AUTO_TTS"] = False
    await interaction.response.send_message("🔇 Auto TTS: TẮT", ephemeral=True)

@bot.tree.command(name="out", guild=discord.Object(id=GUILD_ID))
async def out(interaction: discord.Interaction):
    if interaction.guild.voice_client:
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("👋 Tạm biệt")
    else:
        await interaction.response.send_message("Bot đang không ở trong voice")

# ==========================================
# KHỞI CHẠY (VỚI CƠ CHẾ TỰ RESTART)
# ==========================================
def main():
    # Chạy Web server
    Thread(target=run_web, daemon=True).start()

    retry_count = 0
    while True:
        try:
            bot.run(TOKEN)
        except discord.errors.HTTPException as e:
            if e.status == 429:
                retry_count += 1
                wait_time = min(2**retry_count, 300) # Đợi lũy thừa (2s, 4s, 8s... max 5 phút)
                print(f"🔥 LỖI 429 (Rate Limit). Thử lại sau {wait_time} giây...")
                # Nếu bị chặn quá nặng, thoát code để Render tự cấp IP mới
                if retry_count > 5:
                    print("Quá nhiều lỗi 429, yêu cầu Render đổi IP...")
                    sys.exit(1) 
                
                import time
                time.sleep(wait_time)
            else:
                print(f"Lỗi HTTP: {e}")
                break
        except Exception as e:
            print(f"Lỗi không xác định: {e}")
            break

if __name__ == "__main__":
    main()
