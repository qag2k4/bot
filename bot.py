# ==========================================
# GLOBAL STATE
# ==========================================
class BotState:
    def __init__(self):
        self.AUTO_TTS = False
        self.TTS_CHANNEL_ID = None
        self.tts_queues = {}
        self.tts_tasks = {}

state = BotState()


# ==========================================
# TTS HELPER
# ==========================================
async def tts_worker(guild):
    guild_id = guild.id
    queue = state.tts_queues[guild_id]

    while True:
        text = await queue.get()

        try:
            if not guild.voice_client:
                queue.task_done()
                continue

            text = clean_tts_text(text)
            if not text:
                queue.task_done()
                continue

            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
                tts = gTTS(text=text, lang='vi')
                tts.save(fp.name)
                temp_path = fp.name

            done = asyncio.Event()

            def after_playing(error):
                try:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                except:
                    pass

                if error:
                    print(f"❌ Lỗi phát audio: {error}")

                bot_loop = guild.voice_client.client.loop
                bot_loop.call_soon_threadsafe(done.set)

            source = discord.FFmpegPCMAudio(temp_path)

            while guild.voice_client.is_playing() or guild.voice_client.is_paused():
                await asyncio.sleep(0.2)

            guild.voice_client.play(source, after=after_playing)

            await done.wait()

        except Exception as e:
            print(f"❌ Lỗi TTS worker: {e}")

        finally:
            queue.task_done()


async def play_tts(guild, text):
    if not guild or not guild.voice_client:
        return

    text = clean_tts_text(text)
    if not text:
        return

    guild_id = guild.id

    if guild_id not in state.tts_queues:
        state.tts_queues[guild_id] = asyncio.Queue()

    await state.tts_queues[guild_id].put(text)

    if guild_id not in state.tts_tasks or state.tts_tasks[guild_id].done():
        state.tts_tasks[guild_id] = asyncio.create_task(tts_worker(guild))
