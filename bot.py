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
# CẤU HÌNH BOT
# ==========================================
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

speech_lock = asyncio.Lock()
voice_lock = asyncio.Lock()

AUTO_TTS = False
TTS_CHANNEL_ID = None
last_tts_time = {}

# ==========================================
# HÀM PHỤ
# ==========================================
async def cleanup_voice(guild: discord.Guild):
    vc = guild.voice_client
    if vc:
        try:
            await vc.disconnect(force=True)
        except Exception as e:
            print("CLEANUP VOICE ERROR:", repr(e))


async def ensure_voice(interaction: discord.Interaction):
    async with voice_lock:
        if not interaction.user.voice or not interaction.user.voice.channel:
            return None, "❌ Bạn chưa vào Voice!"

        channel = interaction.user.voice.channel
        vc = interaction.guild.voice_client

        try:
            if vc and vc.is_connected():
                if vc.channel and vc.channel.id == channel.id:
                    return vc, None

                await vc.move_to(channel)
                return interaction.guild.voice_client, None

            if vc and not vc.is_connected():
                await cleanup_voice(interaction.guild)

            vc = await channel.connect(timeout=30.0, reconnect=True, self_deaf=True)
            return vc, None

        except Exception as e:
            print("ENSURE VOICE ERROR:", repr(e))
            await cleanup_voice(interaction.guild)
            return None, f"❌ Lỗi voice: {type(e).__name__}: {e}"


async def play_tts(vc, text):
    async with speech_lock:
        filename = os.path.join(tempfile.gettempdir(), f"{uuid.uuid4()}.mp3")

        try:
            # giới hạn độ dài
            if len(text) > 200:
                text = text[:200]

            tts = gTTS(text=text, lang='vi')
            await asyncio.to_thread(tts.save, filename)

            if not vc or not vc.is_connected():
                return

            while vc.is_playing() or vc.is_paused():
                await asyncio.sleep(0.2)

            source = discord.FFmpegPCMAudio(filename, options="-vn")

            def after_playing(error):
                if error:
                    print("PLAYBACK ERROR:", repr(error))
                if os.path.exists(filename):
                    try:
                        os.remove(filename)
                    except Exception:
                        pass

            vc.play(source, after=after_playing)

            while vc.is_playing():
                await asyncio.sleep(0.2)

        except Exception as e:
            print("PLAY TTS ERROR:", repr(e))
            if os.path.exists(filename):
                try:
                    os.remove(filename)
                except Exception:
                    pass


# ==========================================
# EVENT
# ==========================================
@bot.event
async def on_ready():
    try:
        await bot.tree.sync()
    except Exception as e:
        print("SYNC ERROR:", repr(e))
    print(f"✅ Bot online: {bot.user}")


@bot.event
async def on_voice_state_update(member, before, after):
    vc = member.guild.voice_client
    if not vc or not vc.channel:
        return

    if before.channel and vc.channel and before.channel.id == vc.channel.id:
        humans = [m for m in vc.channel.members if not m.bot]

        if len(humans) == 0:
            await asyncio.sleep(60)

            vc = member.guild.voice_client
            if not vc or not vc.channel:
                return

            humans = [m for m in vc.channel.members if not m.bot]
            if len(humans) == 0:
                try:
                    await vc.disconnect(force=True)
                    print(f"🔌 Tự out vì phòng trống.")
                except Exception as e:
                    print("AUTO DISCONNECT ERROR:", repr(e))


@bot.event
async def on_message(message: discord.Message):
    global AUTO_TTS, TTS_CHANNEL_ID, last_tts_time

    if message.author.bot or not AUTO_TTS:
        return

    if TTS_CHANNEL_ID and message.channel.id != TTS_CHANNEL_ID:
        return

    if not message.guild:
        return

    vc = message.guild.voice_client
    if not vc or not vc.is_connected():
        return

    if not message.author.voice or message.author.voice.channel != vc.channel:
        return

    content = message.content.strip()
    if not content:
        return

    # chống spam nhẹ
    now = asyncio.get_event_loop().time()
    uid = message.author.id

    if uid in last_tts_time and now - last_tts_time[uid] < 2:
        return

    last_tts_time[uid] = now

    await play_tts(vc, content)


# ==========================================
# SLASH COMMAND
# ==========================================
@bot.tree.command(name="join", description="Vào voice")
async def join(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    vc, err = await ensure_voice(interaction)
    if err:
        return await interaction.followup.send(err)

    await interaction.followup.send(f"✅ Đã vào {vc.channel.name}")


@bot.tree.command(name="n", description="TTS")
async def n(interaction: discord.Interaction, text: str):
    if not interaction.user.voice or not interaction.user.voice.channel:
        return await interaction.response.send_message("❌ Bạn chưa vào Voice!", ephemeral=True)

    await interaction.response.send_message(f"📢: {text}", ephemeral=True)

    vc, err = await ensure_voice(interaction)
    if err:
        return await interaction.followup.send(err, ephemeral=True)

    await play_tts(vc, text)


@bot.tree.command(name="auto", description="Auto đọc")
async def auto(interaction: discord.Interaction):
    global AUTO_TTS, TTS_CHANNEL_ID
    AUTO_TTS = True
    TTS_CHANNEL_ID = interaction.channel.id
    await interaction.response.send_message("🎙️ AUTO: ON", ephemeral=True)


@bot.tree.command(name="tat", description="Tắt auto")
async def tat(interaction: discord.Interaction):
    global AUTO_TTS
    AUTO_TTS = False
    await interaction.response.send_message("🔇 AUTO: OFF", ephemeral=True)


@bot.tree.command(name="out", description="Thoát voice")
async def out(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc:
        await vc.disconnect(force=True)
        await interaction.response.send_message("👋 Bye", ephemeral=True)
    else:
        await interaction.response.send_message("Không ở voice", ephemeral=True)


@bot.tree.command(name="resetvoice", description="Reset voice")
async def resetvoice(interaction: discord.Interaction):
    await cleanup_voice(interaction.guild)
    await interaction.response.send_message("🔄 Reset xong", ephemeral=True)


bot.run(TOKEN)
