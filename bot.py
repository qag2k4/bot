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
bot = commands.Bot(command_prefix="!", intents=intents)

speech_lock = asyncio.Lock()

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
                
        except Exception as e:
            print(f"Lỗi: {e}")
            if os.path.exists(filename):
                try: os.remove(filename)
                except: pass

@bot.tree.command(name="join", description="Mời bot vào phòng")
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
        await interaction.followup.send(f"✅ Đã vào **{channel.name}**")
    except Exception as e:
        await interaction.followup.send(f"Lỗi: {e}")

@bot.tree.command(name="n", description="Bot nói nội dung")
async def n(interaction: discord.Interaction, text: str):
    # Thay thế dòng chữ dài bằng icon cái loa và nội dung
    await interaction.response.send_message(f"📢: {text}", ephemeral=False)

    if not interaction.user.voice:
        return await interaction.followup.send("❌ Vào voice trước!", ephemeral=True)

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

@bot.tree.command(name="out", description="Cho bot thoát")
async def out(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc:
        await vc.disconnect(force=True)
        await interaction.response.send_message("👋 Tạm biệt!")
    else:
        await interaction.response.send_message("Bot không trong Voice.", ephemeral=True)

bot.run(TOKEN)
