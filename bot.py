import discord
from discord.ext import commands
import asyncio
import aiohttp
import os
from dotenv import load_dotenv
import yt_dlp

# ---------- ENV ----------
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
ELEVEN_API_KEY = os.getenv("ELEVEN_API_KEY")
VOICE_ID = os.getenv("VOICE_ID")
NEWS_CHANNEL_ID = int(os.getenv("NEWS_CHANNEL_ID", 0))

# ---------- DISCORD ----------
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

music_queue = asyncio.Queue()
news_queue = asyncio.Queue()
is_playing_news = False

# ---------- ELEVENLABS ----------
async def generate_tts(text, filename="news.mp3"):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"

    headers = {
        "xi-api-key": ELEVEN_API_KEY,
        "Content-Type": "application/json"
    }

    data = {
        "text": text,
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.7
        }
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=data, headers=headers) as response:
            if response.status != 200:
                print("TTS ERROR:", await response.text())
                return None

            audio = await response.read()

            with open(filename, "wb") as f:
                f.write(audio)

            return filename

# ---------- YOUTUBE ----------
ytdl_opts = {
    "format": "bestaudio/best",
    "quiet": True,
    "noplaylist": False
}

ffmpeg_opts = {
    "options": "-vn"
}

ytdl = yt_dlp.YoutubeDL(ytdl_opts)


async def extract_streams(url):
    loop = asyncio.get_event_loop()

    data = await loop.run_in_executor(
        None, lambda: ytdl.extract_info(url, download=False)
    )

    # 🎵 PLAYLIST
    if "entries" in data:
        return [entry["url"] for entry in data["entries"] if entry]

    # 🎵 SINGLE
    return [data["url"]]


# ---------- RADIO LOOP ----------
async def radio_loop(vc):
    global is_playing_news

    while True:
        try:
            # 📰 NEWS FIRST
            if not news_queue.empty():
                is_playing_news = True

                text = await news_queue.get()
                file = await generate_tts(text)

                if file:
                    vc.play(discord.FFmpegPCMAudio(file))

                    while vc.is_playing():
                        await asyncio.sleep(1)

                is_playing_news = False
                continue

            # 🎵 MUSIC
            if not vc.is_playing() and not is_playing_news:
                if not music_queue.empty():
                    url = await music_queue.get()
                    streams = await extract_streams(url)

                    for stream_url in streams:
                        vc.play(discord.FFmpegPCMAudio(stream_url, **ffmpeg_opts))

                        while vc.is_playing():
                            await asyncio.sleep(1)

                        # If breaking news arrives → interrupt
                        if not news_queue.empty():
                            break

                else:
                    await asyncio.sleep(2)

            await asyncio.sleep(1)

        except Exception as e:
            print("RADIO ERROR:", e)
            await asyncio.sleep(2)


# ---------- COMMANDS ----------
@bot.command()
async def join(ctx):
    if not ctx.author.voice:
        await ctx.send("❌ Join a voice channel first.")
        return

    channel = ctx.author.voice.channel

    if ctx.voice_client:
        vc = await ctx.voice_client.move_to(channel)
    else:
        vc = await channel.connect()

    bot.loop.create_task(radio_loop(vc))

    await ctx.send("📻 De Antillen Radio LIVE!")


@bot.command()
async def play(ctx, url: str):
    await music_queue.put(url)
    await ctx.send(f"🎵 Added: {url}")


@bot.command()
async def stop(ctx):
    vc = ctx.voice_client
    if vc:
        vc.stop()
        await ctx.send("⏹️ Stopped")


# ---------- NEWS ----------
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    await bot.process_commands(message)

    if message.channel.id != NEWS_CHANNEL_ID:
        return

    content = message.content.upper()

    vc = discord.utils.get(bot.voice_clients, guild=message.guild)
    if not vc:
        return

    if "[IGNORE]" in content:
        return

    if "[BREAKING]" in content:
        if vc.is_playing():
            vc.stop()
        await news_queue.put(message.content)

    elif "[NORMAL]" in content:
        await news_queue.put(message.content)


# ---------- READY ----------
@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")


# ---------- START ----------
if not TOKEN:
    raise ValueError("DISCORD_TOKEN missing")

bot.run(TOKEN)