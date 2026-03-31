# De Antillen Discord Radio Bot (Starter with .env)

import discord
from discord.ext import commands
import asyncio
import requests
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
ELEVEN_API_KEY = os.getenv("ELEVEN_API_KEY")
VOICE_ID = os.getenv("VOICE_ID")
NEWS_CHANNEL_ID = int(os.getenv("NEWS_CHANNEL_ID"))

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

music_queue = asyncio.Queue()
news_queue = asyncio.Queue()
is_playing_news = False

# ---------- ELEVENLABS ----------
def generate_tts(text, filename="news.mp3"):
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

    response = requests.post(url, json=data, headers=headers)

    if response.status_code != 200:
        print("ElevenLabs error:", response.text)
        return None

    with open(filename, "wb") as f:
        f.write(response.content)

    return filename

# ---------- AUDIO ----------
def play_audio(vc, file_path, after=None):
    source = discord.FFmpegPCMAudio(file_path, executable="ffmpeg")
    vc.play(source, after=after)

async def play_next(vc):
    global is_playing_news

    if not news_queue.empty():
        is_playing_news = True
        text = await news_queue.get()
        file = generate_tts(text)

        if not file:
            return

        def after_news(err):
            global is_playing_news
            is_playing_news = False
            asyncio.run_coroutine_threadsafe(play_next(vc), bot.loop)

        play_audio(vc, file, after=after_news)
        return

    if not music_queue.empty():
        is_playing_news = False
        file = await music_queue.get()

        def after_music(err):
            asyncio.run_coroutine_threadsafe(play_next(vc), bot.loop)

        play_audio(vc, file, after=after_music)

# ---------- COMMANDS ----------
@bot.command()
async def join(ctx):
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        await channel.connect()
        await ctx.send("Joined voice channel")
    else:
        await ctx.send("You are not in a voice channel")

@bot.command()
async def play(ctx, url: str):
    await music_queue.put(url)

    vc = ctx.voice_client
    if vc and not vc.is_playing():
        await play_next(vc)

@bot.command()
async def stop(ctx):
    vc = ctx.voice_client
    if vc:
        vc.stop()
        await ctx.send("Stopped playback")

# ---------- NEWS LISTENER ----------
@bot.event
async def on_message(message):
    await bot.process_commands(message)

    if message.channel.id != NEWS_CHANNEL_ID:
        return

    content = message.content.upper()

    if "[IGNORE]" in content:
        return

    vc = discord.utils.get(bot.voice_clients, guild=message.guild)
    if not vc:
        return

    if "[BREAKING]" in content:
        vc.stop()
        await news_queue.put(message.content)
        await play_next(vc)

    elif "[NORMAL]" in content:
        await news_queue.put(message.content)

# ---------- RUN ----------
bot.run(TOKEN)