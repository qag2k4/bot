import os
import asyncio
import discord
from discord.ext import commands
from gtts import gTTS
import uuid
import tempfile
from flask import Flask
from threading import Thread

# WEB SERVER ĐỂ GIỮ RENDER KHÔNG TẮT
app = Flask('')
@app.route('/')
def home(): return "Bot is alive"
@app.route('/healthz')
def healthz(): return "OK"
def run(): app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 10000)))

Thread(target=run).start()

# CẤU HÌNH BOT
TOKEN = os.getenv("DISCORD_TOKEN")
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Bot logged in as {bot.user}")

async def speak_text(vc, text):
    filename = os.path.join(tempfile.gettempdir(), f"{uuid.uuid4()}.mp3")
    try:
        # Tạo file TTS
        tts = gTTS(text=text, lang='vi')
        await asyncio.to_thread(tts.save, filename)

        # Đợi một chút để file kịp lưu vào ổ đĩa Docker
        await asyncio.sleep(0.5)

        # Cấu hình FFmpeg nhẹ nhất có thể
        source = discord.FFmpegPCMAudio(filename, options="-vn")
        
        if not vc.is_playing():
            vc.play(source, after=lambda e: os.remove(filename) if os.path.exists(filename) else None)
            
            while vc.is_playing():
                await asyncio.sleep(1)
    except Exception as e:
        print(f"Lỗi phát âm thanh: {e}")
        if os.path.exists(filename): os.remove(filename)

@bot.tree.command(name="n", description="Nói gì đó")
async def n(interaction: discord.Interaction, text: str):
    if not interaction.user.voice:
        return await interaction.response.send_message("Vào voice trước đã!")

    await interaction.response.defer()
    
    channel = interaction.user.voice.channel
    vc = interaction.guild.voice_client

    try:
        if not vc:
            vc = await channel.connect(timeout=20.0, self_deaf=True)
        elif vc.channel != channel:
            await vc.move_to(channel)
        
        await speak_text(vc, text)
        await interaction.followup.send(f"Đã nói: {text}")
    except Exception as e:
        await interaction.followup.send(f"Lỗi kết nối: {e}")
        if vc: await vc.disconnect()

@bot.tree.command(name="out", description="Thoát voice")
async def out(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc:
        await vc.disconnect()
        await interaction.response.send_message("Bot đã thoát.")
    else:
        await interaction.response.send_message("Bot không ở trong phòng nào.")

bot.run(TOKEN)
