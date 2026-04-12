import os
import re
import uuid
import tempfile
import asyncio
from collections import deque
from threading import Thread
from flask import Flask

import discord
from discord.ext import commands
from gtts import gTTS
from dotenv import load_dotenv

print("BOT.PY STARTING...")

load_dotenv()

# ==========================================
# WEB SERVER (Chống sập Render)
# ==========================================
app = Flask(__name__)
@app.route('/')
def home():
    return "Bot hoạt động hoàn hảo!"

@app.route('/healthz')
def healthz():
    return "OK"

def run_server():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

Thread(target=run_server, daemon=True).start()
# ==========================================

TOKEN = os.getenv("DISCORD_TOKEN")
print("DISCORD_TOKEN exists:", bool(TOKEN))

FFMPEG_PATH = "ffmpeg"
GUILD_ID = 1440581960069287939
MY_GUILD = discord.Object(id=GUILD_ID)

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

AUTO_TTS = False
TTS_TEXT_CHANNEL_ID = None
tts_queue = deque()
is_speaking = False

def clean_text(text: str) -> str:
    text = re.sub(r"http\S+", "", text)
    text = re.sub(r"<@!?\d+>", "", text)
    text = re.sub(r"[^\w\sÀ-ỹ]", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def add_to_queue(vc: discord.VoiceClient, text: str):
    text = clean_text(text)
    if not text:
        return
    tts_queue.append((vc, text))
    asyncio.create_task(play_next())

async def generate_tts_file(text: str, filename: str):
    def _save():
        gTTS(text=text, lang="vi").save(filename)
    await asyncio.to_thread(_save)

async def play_next():
    global is_speaking

    if is_speaking:
        return
    if not tts_queue:
        return

    is_speaking = True

    try:
        while tts_queue:
            vc, text = tts_queue.popleft()

            if not vc or not vc.is_connected():
                print("Skip queue item: voice client not connected")
                continue

            filename = os.path.join(tempfile.gettempdir(), f"tts_{uuid.uuid4().hex}.mp3")

            try:
                print("Generating TTS:", text)
                await asyncio.wait_for(generate_tts_file(text, filename), timeout=20)

                if not vc.is_connected():
                    print("Voice disconnected before play")
                    try:
                        if os.path.exists(filename):
                            os.remove(filename)
                    except Exception:
                        pass
                    continue

                finished = asyncio.Event()

                # VÁ LỖI FFMPEG BẰNG BEFORE_OPTIONS
                ffmpeg_options = {
                    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
                    'options': '-vn'
                }
                source = discord.FFmpegPCMAudio(filename, executable=FFMPEG_PATH, **ffmpeg_options)

                def after_play(err):
                    if err:
                        print("FFmpeg after_play error:", repr(err))
                    try:
                        if os.path.exists(filename):
                            os.remove(filename)
                    except Exception:
                        pass
                    bot.loop.call_soon_threadsafe(finished.set)

                print("Start playing audio")
                vc.play(source, after=after_play)
                await finished.wait()
                print("Finished playing audio")

            except asyncio.TimeoutError:
                print("TTS timeout for text:", text)
                try:
                    if os.path.exists(filename):
                        os.remove(filename)
                except Exception:
                    pass
            except Exception as e:
                print("Lỗi TTS:", repr(e))
                try:
                    if os.path.exists(filename):
                        os.remove(filename)
                except Exception:
                    pass
    finally:
        is_speaking = False

@bot.event
async def on_ready():
    if not discord.opus.is_loaded():
        try:
            discord.opus.load_opus('libopus.so.0')
            print("=> Đã tải thành công thư viện âm thanh Opus!")
        except Exception as e:
            print("=> Cảnh báo: Không thể tải thủ công Opus:", e)

    try:
        bot.tree.clear_commands(guild=None)
        await bot.tree.sync(guild=None)
        synced = await bot.tree.sync(guild=MY_GUILD)
        print("=========================================")
        print(f"Bot online: {bot.user}")
        print(f"ĐÃ KIẾN TRÚC LẠI LUỒNG ASYNC & VÁ LỖI {len(synced)} LỆNH!")
        print("=========================================")
    except Exception as e:
        print("Sync slash lỗi:", repr(e))

@bot.event
async def on_disconnect():
    print("Bot bị ngắt kết nối Discord")

@bot.event
async def on_resumed():
    print("Bot đã reconnect lại Discord")

@bot.event
async def on_voice_state_update(member, before, after):
    if bot.user and member.id == bot.user.id:
        before_name = before.channel.name if before.channel else None
        after_name = after.channel.name if after.channel else None
        print(f"VOICE UPDATE: {before_name} -> {after_name}")

        if before.channel and not after.channel:
            vc = member.guild.voice_client
            if vc:
                try:
                    await vc.disconnect(force=True)
                except:
                    pass
            global is_speaking, tts_queue
            tts_queue.clear()
            is_speaking = False

# HÀM XỬ LÝ BACKGROUND ĐỂ CHỐNG LỖI "KHÔNG PHẢN HỒI"
async def connect_voice_background(channel, guild):
    try:
        vc = guild.voice_client
        if not vc:
            print(f"Background Task: Connecting to {channel.name}")
            await channel.connect(self_deaf=True)
        elif vc.channel != channel:
            await vc.move_to(channel)
    except Exception as e:
        print(f"Background Connect Error: {e}")

@bot.tree.command(name="join", description="Gọi bot vào phòng voice", guild=MY_GUILD)
async def join(interaction: discord.Interaction):
    if not interaction.user.voice:
        await interaction.response.send_message("Bạn cần vào phòng voice trước!", ephemeral=True)
        return

    # Trả lời NGAY LẬP TỨC để Discord không báo đỏ
    await interaction.response.send_message("Đang tiến hành kết nối...", ephemeral=True)
    
    # Ném việc kết nối (chậm) sang một luồng ngầm
    asyncio.create_task(connect_voice_background(interaction.user.voice.channel, interaction.guild))


@bot.tree.command(name="n", description="Bot nói nội dung bạn nhập", guild=MY_GUILD)
async def n(interaction: discord.Interaction, text: str):
    global TTS_TEXT_CHANNEL_ID

    if not interaction.user.voice:
        await interaction.response.send_message("Bạn cần vào phòng voice trước!", ephemeral=True)
        return

    # Trả lời NGAY LẬP TỨC
    await interaction.response.send_message("Đã nhận lệnh, đang tải giọng nói...", ephemeral=True)
    
    TTS_TEXT_CHANNEL_ID = interaction.channel.id
    channel = interaction.user.voice.channel
    
    # Tạo một hàm con chạy ngầm để xử lý vừa connect vừa đọc
    async def process_n_background():
        try:
            vc = interaction.guild.voice_client
            if not vc:
                print(f"Background Task (/n): Connecting to {channel.name}")
                vc = await channel.connect(self_deaf=True)
            elif vc.channel != channel:
                await vc.move_to(channel)
                
            add_to_queue(vc, text)
        except Exception as e:
            print(f"Background Error in /n: {e}")

    # Đẩy vào luồng ngầm
    asyncio.create_task(process_n_background())


@bot.tree.command(name="auto", description="Bật tự động đọc tin nhắn", guild=MY_GUILD)
async def auto(interaction: discord.Interaction):
    global AUTO_TTS
    AUTO_TTS = True
    await interaction.response.send_message("AUTO TTS: BẬT", ephemeral=True)

@bot.tree.command(name="tat", description="Tắt tự động đọc", guild=MY_GUILD)
async def tat(interaction: discord.Interaction):
    global AUTO_TTS
    AUTO_TTS = False
    await interaction.response.send_message("AUTO TTS: TẮT", ephemeral=True)

@bot.tree.command(name="skip", description="Bỏ câu đang đọc", guild=MY_GUILD)
async def skip(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.stop()
        await interaction.followup.send("Đã skip", ephemeral=True)
    else:
        await interaction.followup.send("Bot không nói", ephemeral=True)

@bot.tree.command(name="out", description="Đá bot ra khỏi voice", guild=MY_GUILD)
async def out(interaction: discord.Interaction):
    global is_speaking
    await interaction.response.defer(ephemeral=True)
    vc = interaction.guild.voice_client
    if vc:
        tts_queue.clear()
        is_speaking = False
        if vc.is_playing():
            vc.stop()
        try:
            await vc.disconnect(force=True)
            await interaction.followup.send("Bot đã thoát", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"Lỗi thoát voice: {e}", ephemeral=True)
    else:
        await interaction.followup.send("Bot chưa vào voice", ephemeral=True)

@bot.tree.command(name="reset", description="Làm mới bot khi bị đơ/lag", guild=MY_GUILD)
async def reset_bot(interaction: discord.Interaction):
    global is_speaking, AUTO_TTS, TTS_TEXT_CHANNEL_ID
    await interaction.response.defer(ephemeral=True)
    tts_queue.clear()
    is_speaking = False
    AUTO_TTS = False
    TTS_TEXT_CHANNEL_ID = None
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.stop()
    await interaction.followup.send("Đã dọn dẹp hệ thống! Bot vẫn ở trong phòng.", ephemeral=True)

@bot.event
async def on_message(message: discord.Message):
    await bot.process_commands(message)
    if message.author.bot or not AUTO_TTS:
        return
    if not message.guild or not message.content.strip():
        return
    if TTS_TEXT_CHANNEL_ID and message.channel.id != TTS_TEXT_CHANNEL_ID:
        return
    vc = message.guild.voice_client
    if not vc or not message.author.voice or message.author.voice.channel != vc.channel:
        return
    add_to_queue(vc, message.content)

async def main():
    if not TOKEN:
        raise RuntimeError("DISCORD_TOKEN không tồn tại hoặc đang rỗng")
    print("Starting Discord bot...")
    async with bot:
        await bot.start(TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print("BOT CRASH:", repr(e))
        raise
