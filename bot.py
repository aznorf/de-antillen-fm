import discord
from discord.ext import commands
import asyncio
import aiohttp
import os
from dotenv import load_dotenv

# Chargement des variables d'environnement
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
ELEVEN_API_KEY = os.getenv("ELEVEN_API_KEY")
VOICE_ID = os.getenv("VOICE_ID")
NEWS_CHANNEL_ID = int(os.getenv("NEWS_CHANNEL_ID", 0))

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

music_queue = asyncio.Queue()
news_queue = asyncio.Queue()
is_playing_news = False

# ---------- ELEVENLABS (Version Asynchrone) ----------
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
                error_text = await response.text()
                print(f"Erreur ElevenLabs: {error_text}")
                return None
            
            content = await response.read()
            with open(filename, "wb") as f:
                f.write(content)
            return filename

# ---------- AUDIO ----------
def play_audio(vc, file_path, after_callback):
    # Sur Railway, ffmpeg doit être installé via apt.txt
    source = discord.FFmpegPCMAudio(file_path)
    vc.play(source, after=lambda e: bot.loop.create_task(after_callback(e)))

async def play_next(vc):
    global is_playing_news

    # Priorité aux infos (News)
    if not news_queue.empty():
        is_playing_news = True
        text = await news_queue.get()
        file = await generate_tts(text)

        if not file:
            is_playing_news = False
            return

        async def after_news(err):
            global is_playing_news
            is_playing_news = False
            await play_next(vc)

        play_audio(vc, file, after_news)
        return

    # Sinon, on joue la musique
    if not music_queue.empty():
        is_playing_news = False
        file = await music_queue.get()

        async def after_music(err):
            await play_next(vc)

        play_audio(vc, file, after_music)

# ---------- COMMANDES ----------
@bot.command()
async def join(ctx):
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        await channel.connect()
        await ctx.send("✅ Radio De Antillen en ligne !")
    else:
        await ctx.send("Tu dois être dans un salon vocal.")

@bot.command()
async def play(ctx, url: str):
    await music_queue.put(url)
    vc = ctx.voice_client
    if vc and not vc.is_playing():
        await play_next(vc)
    await ctx.send(f"Ajouté à la file : {url}")

@bot.command()
async def stop(ctx):
    vc = ctx.voice_client
    if vc:
        vc.stop()
        await ctx.send("Musique arrêtée.")

# ---------- LISTENER DE NEWS ----------
@bot.event
async def on_message(message):
    # Important : ne pas oublier de traiter les commandes
    await bot.process_commands(message)

    if message.channel.id != NEWS_CHANNEL_ID or message.author.bot:
        return

    content = message.content.upper()
    if "[IGNORE]" in content:
        return

    vc = discord.utils.get(bot.voice_clients, guild=message.guild)
    if not vc:
        return

    if "[BREAKING]" in content:
        # On coupe la musique immédiatement pour l'info urgente
        if vc.is_playing():
            vc.stop()
        await news_queue.put(message.content)
        await play_next(vc)

    elif "[NORMAL]" in content:
        await news_queue.put(message.content)
        if not vc.is_playing():
            await play_next(vc)

@bot.event
async def on_ready():
    print(f'Connecté en tant que {bot.user.name}')

# ---------- DEMARRAGE ----------
if TOKEN:
    bot.run(TOKEN)
else:
    print("ERREUR : Le TOKEN est manquant. Vérifie tes variables d'environnement.")